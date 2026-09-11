"""Append-only official availability captures for upcoming regular-season games.

capture_availability(games, roster, expected_qbs, output, *, purpose='forecast', now=None, fetch=None)
returns a mapping with games keyed by game_id. Inputs are normalized game dicts,
fresh roster rows, and TEAM -> expected GSIS ID. No forecast or rating is changed.
fetch, when supplied, returns {body: bytes, status: 200, final_url: HTTPS_URL}.
load_availability(directory) verifies hashes and replays offline from saved bytes.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

import generate_site
from pgo_challenger import _normalize_player_name, _unique_roster_name_ids
from pgo_sources import normalize_team
from research.pgo_postseason_candidate.sources import injury_tables


REPORT_URL = 'https://www.nfl.com/injuries/'
NFL_NEWS_URL = 'https://www.nfl.com/news/'
TEAM_NAMES = {value[0]: name for name, value in generate_site.TEAM.items()}
TEAM_DOMAINS = dict(zip(
    'ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LAC LAR LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS'.split(),
    ('azcardinals.com atlantafalcons.com baltimoreravens.com buffalobills.com panthers.com chicagobears.com '
     'bengals.com clevelandbrowns.com dallascowboys.com denverbroncos.com detroitlions.com packers.com '
     'houstontexans.com colts.com jaguars.com chiefs.com chargers.com therams.com raiders.com miamidolphins.com '
     'vikings.com patriots.com neworleanssaints.com giants.com newyorkjets.com philadelphiaeagles.com '
     'steelers.com seahawks.com 49ers.com buccaneers.com tennesseetitans.com commanders.com').split()))
UNAVAILABLE = {'OUT', 'INACTIVE', 'EMERGENCY_QB'}
POSITIONS = set('QB RB FB WR TE OL C G T OG OT DL DT DE NT LB ILB OLB EDGE DB CB S FS SS K P LS'.split())


def _utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Availability timestamps require a timezone')
    return value.astimezone(timezone.utc)


def _clock(now=None):
    return _utc(now) if now is not None else datetime.now(timezone.utc)


def _json(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _url(value, team=None, kind=None):
    parsed = urlsplit(value)
    hosts = {'nfl.com', 'www.nfl.com'} if team is None else {TEAM_DOMAINS[team], 'www.' + TEAM_DOMAINS[team]}
    if (parsed.scheme != 'https' or parsed.hostname not in hosts or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.query or parsed.fragment):
        raise ValueError('Availability source is not an allowed official HTTPS URL')
    if kind == 'official_report' and parsed.path.rstrip('/') != '/injuries':
        raise ValueError('Official injury source path differs')
    if kind in ('team_news', 'league_news', 'official_inactives') and not parsed.path.startswith('/news'):
        raise ValueError('Official club source must be a news page')
    return value


def _inputs(games, roster, expected_qbs, checked_at, purpose='forecast'):
    now = _utc(checked_at)
    if purpose not in ('forecast', 'context'):
        raise ValueError('Unknown availability purpose')
    indexed, seen_games, used_teams = {}, set(), set()
    for row in roster:
        row = dict(row, team=normalize_team(row.get('team', '')))
        if row.get('team') not in TEAM_NAMES or not row.get('full_name') or not row.get('position'):
            raise ValueError('Roster identity is incomplete or team is noncanonical')
        gsis = row.get('gsis_id')
        if not gsis and row.get('status') != 'ACT':
            continue
        if not isinstance(gsis, str) or not re.fullmatch(r'00-\d{7}', gsis) or gsis in indexed:
            raise ValueError('Missing or duplicate roster GSIS identity')
        indexed[gsis] = row
    for game in games:
        season, week = game.get('season'), game.get('week')
        home, away = game.get('home'), game.get('away')
        game_id = game.get('game_id', '')
        parts = game_id.split('_') if isinstance(game_id,str) else []
        bound_id = (len(parts) == 4 and parts[:2] == [str(season),f'{week:02d}' if type(week) is int else '']
                    and normalize_team(parts[2]) == away and normalize_team(parts[3]) == home)
        if (type(season) is not int or type(week) is not int or not 1 <= week <= 18
                or home not in TEAM_NAMES or away not in TEAM_NAMES or home == away
                or game.get('game_type') != 'REG'
                or not bound_id
                or game['game_id'] in seen_games or home in used_teams or away in used_teams):
            raise ValueError('Invalid or duplicate availability game identity')
        kickoff, cutoff = _utc(game['kickoff']), _utc(game['lock_at'])
        if cutoff != kickoff - timedelta(minutes=60):
            raise ValueError('Availability cutoff differs from T-60')
        if purpose == 'forecast' and not now < cutoff:
            raise ValueError('Availability capture must finish before the T-60 lock')
        if purpose == 'context' and not kickoff-timedelta(hours=24) <= now <= kickoff+timedelta(hours=6):
            raise ValueError('Availability context must finish within 24 hours before through 6 hours after kickoff')
        seen_games.add(game['game_id'])
        used_teams.update((home, away))
        for team in (home, away):
            row = indexed.get(expected_qbs.get(team))
            if not row or row['team'] != team or row['position'] != 'QB' or row.get('status') != 'ACT':
                raise ValueError('Expected quarterback requires a matching current ACT QB roster identity')
    if not games:
        raise ValueError('Availability capture requires upcoming games')
    return indexed


class _Page(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.scripts, self.links = [], []
        self.script, self.link = None, None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.script = []
        if tag == 'a' and attrs.get('href'):
            self.link = [attrs['href'], []]

    def handle_endtag(self, tag):
        if tag == 'script' and self.script is not None:
            self.scripts.append(''.join(self.script))
            self.script = None
        if tag == 'a' and self.link is not None:
            self.links.append((self.link[0], ' '.join(self.link[1])))
            self.link = None

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)
        if self.link is not None:
            self.link[1].append(data)


def _parse_final_inactives_v1(raw, game, team, captured_at):
    """Admit only a dated matchup article with a recognizable team inactive list."""
    if team not in (game['home'],game['away']):
        raise ValueError('Inactive source team is outside the matchup')
    text = raw.decode('utf-8')
    # Club pages may append unrelated article JSON-LD after the main article.
    main = text.split('<article', 1)[0]
    articles = []
    for script in _Page(main).scripts:
        value = json.loads(script)
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, dict) and item.get('@type') in ('NewsArticle', 'Article') and item.get('articleBody'):
                articles.append(item)
    if len(articles) != 1:
        raise ValueError('No unique official inactive article')
    article = articles[0]
    headline = article.get('headline', '')
    if not re.search(r'\binactive(?:s)?\b', headline, re.I) or not all(
            TEAM_NAMES[t].split()[-1].casefold() in headline.casefold() for t in (game['home'], game['away'])):
        raise ValueError('Inactive article does not identify this matchup')
    if any(int(week) != game['week'] for week in re.findall(r'\bweek\s+(\d+)\b',headline,re.I)):
        raise ValueError('Inactive article identifies a different week')
    published = _utc(article['datePublished'])
    modified = _utc(article.get('dateModified', article['datePublished']))
    kickoff, captured = _utc(game['kickoff']), _utc(captured_at)
    if not kickoff - timedelta(hours=24) <= published <= modified <= min(captured, kickoff):
        raise ValueError('Inactive article publication/modification is outside the pregame capture window')
    body = html.unescape(article['articleBody']).replace('\\n', '\n')
    positions = '|'.join(sorted(POSITIONS, key=len, reverse=True))
    team_heading = (re.escape(TEAM_NAMES[team]) + r'\s*(?:INACTIVES\s*:?)?\s*|'
                    + re.escape(TEAM_NAMES[team].split()[-1]) + r"['’]?\s+INACTIVES\s*:?\s*")
    heading = re.search(r'(?:' + team_heading + r')(?=(?:' + positions + r')\s)', body, re.I)
    if not heading:
        raise ValueError('No structured inactive list for this team')
    section = body[heading.end():]
    other = game['away'] if team == game['home'] else game['home']
    section = re.split(re.escape(TEAM_NAMES[other]), section, maxsplit=1, flags=re.I)[0]
    observations, unparsed = [], []
    for line in (s.strip().lstrip('-*• ').strip() for s in section.splitlines()):
        if not line:
            continue
        match = re.fullmatch(r'(' + positions + r')\s+([^()]+?)(?:\s*\(([^()]*)\))?', line)
        if not match:
            unparsed.append(line)
            continue
        position, name, note = match.groups()
        note = note or ''
        observations.append(dict(name=name.strip(), position=position,
                                 status='EMERGENCY_QB' if position == 'QB' and 'emergency' in note.casefold() else 'INACTIVE',
                                 designation_note=note, source_text=line))
    if not observations or len(observations) > 32 or len({o['name'] for o in observations}) != len(observations):
        raise ValueError('Missing, oversized or duplicate official inactive list')
    return dict(observations=observations, unparsed_lines=unparsed, published_at=published.isoformat(),
                modified_at=modified.isoformat(), headline=headline)


def _team_pattern(team):
    aliases = [TEAM_NAMES[team], TEAM_NAMES[team].split()[-1], team]
    if team == 'SF':
        aliases.append('Niners')
    return '(?:' + '|'.join(re.escape(name) for name in sorted(set(aliases), key=len, reverse=True)) + ')'


def _matches_matchup(text, game):
    named = all(re.search(r'(?<![A-Za-z0-9])' + _team_pattern(t) + r'(?![A-Za-z0-9])', text, re.I)
                for t in (game['home'], game['away']))
    tags = '|'.join(re.escape(a+'vs'+b) for a,b in ((game['home'],game['away']),(game['away'],game['home'])))
    return bool(named or re.search(r'(?<![A-Za-z0-9])(?:' + tags + r')(?![A-Za-z0-9])', text, re.I))


def parse_final_inactives(raw, game, team, captured_at, *, parser_version=2):
    """Version 2 admits observed league headings and dated club list introductions."""
    if type(parser_version) is not int or parser_version not in (1,2):
        raise ValueError('Unsupported availability parser version')
    if parser_version == 1:
        return _parse_final_inactives_v1(raw, game, team, captured_at)
    if team not in (game['home'],game['away']):
        raise ValueError('Inactive source team is outside the matchup')
    articles = []
    for script in _Page(raw.decode('utf-8').split('<article',1)[0]).scripts:
        value = json.loads(script)
        for item in value if isinstance(value,list) else [value]:
            if isinstance(item,dict) and item.get('@type') in ('NewsArticle','Article') and item.get('articleBody'):
                articles.append(item)
    if len(articles) != 1:
        raise ValueError('No unique official inactive article')
    article = articles[0]; headline = article.get('headline','')
    if not re.search(r'\binactive(?:s)?\b',headline,re.I) or not _matches_matchup(headline,game):
        raise ValueError('Inactive article does not identify this matchup')
    if any(int(week) != game['week'] for week in re.findall(r'\bweek\s+(\d+)\b',headline,re.I)):
        raise ValueError('Inactive article identifies a different week')
    published = _utc(article['datePublished']); modified = _utc(article.get('dateModified',article['datePublished']))
    kickoff, captured = _utc(game['kickoff']), _utc(captured_at)
    if not kickoff-timedelta(hours=24) <= published <= modified <= min(captured,kickoff):
        raise ValueError('Inactive article publication/modification is outside the pregame capture window')
    body = html.unescape(article['articleBody']).replace('\\n','\n')
    headings = []
    for candidate in (game['home'],game['away']):
        other = game['away'] if candidate == game['home'] else game['home']
        label = _team_pattern(candidate)
        pattern = (r'^[ \t]*(?:' + label + r"(?:['\u2019]s?|')?\s*(?:inactives\s*:?)?|"
                   r'Here are (?:the )?' + label + r' inactives for Week\s+(\d+)\s+against (?:the )?'
                   + _team_pattern(other) + r':?)[ \t]*$')
        for match in re.finditer(pattern,body,re.I|re.M):
            if match[1] and int(match[1]) != game['week']:
                raise ValueError('Inactive list heading identifies a different week')
            headings.append((match.start(),match.end(),candidate))
    headings.sort()
    selected = [index for index,value in enumerate(headings) if value[2] == team]
    if not selected:
        # Preserve supported older club formats, including concatenated headings.
        return _parse_final_inactives_v1(raw,game,team,captured_at)
    if len(selected) != 1:
        raise ValueError('Ambiguous inactive list headings')
    index = selected[0]; start = headings[index][1]
    end = headings[index+1][0] if index+1 < len(headings) else len(body)
    positions = '|'.join(sorted(POSITIONS,key=len,reverse=True))
    observations, unparsed = [], []
    for line in (s.strip().lstrip('-*\u2022 ').strip() for s in body[start:end].splitlines()):
        if not line:
            continue
        match = re.fullmatch(r'(' + positions + r')\s+([^()]+?)(?:\s*\(([^()]*)\))?',line)
        if not match:
            unparsed.append(line); continue
        position, name, note = match.groups(); note = note or ''
        observations.append(dict(name=name.strip(),position=position,
            status='EMERGENCY_QB' if position == 'QB' and 'emergency' in note.casefold() else 'INACTIVE',
            designation_note=note,source_text=line))
    if not observations or len(observations)>32 or len({r['name'] for r in observations}) != len(observations):
        raise ValueError('Missing, oversized or duplicate official inactive list')
    return dict(observations=observations,unparsed_lines=unparsed,published_at=published.isoformat(),
                modified_at=modified.isoformat(),headline=headline)


def build_availability(games, roster, expected_qbs, sources, *, checked_at, purpose='forecast', parser_version=2):
    """Pure replay of supplied raw official captures; unknown never means healthy."""
    now = _utc(checked_at)
    if type(parser_version) is not int or parser_version not in (1,2) or (parser_version == 1 and purpose != 'forecast'):
        raise ValueError('Unsupported availability parser version/purpose')
    indexed = _inputs(games, roster, expected_qbs, now, purpose)
    names = {team: _unique_roster_name_ids([r for r in indexed.values() if r['team'] == team], [])[0]
             for team in {t for g in games for t in (g['home'], g['away'])}}
    admitted, metadata, urls = [], [], set()
    for source in sources:
        kind, team = source['kind'], source.get('team')
        legacy_source = kind in ('official_report','team_news','official_inactives') and (kind == 'official_report') == (team is None)
        league_source = parser_version == 2 and team is None and kind in ('league_news','official_inactives')
        if not (legacy_source or league_source):
            raise ValueError('Invalid availability source kind/team')
        if team is not None and team not in TEAM_NAMES:
            raise ValueError('Invalid source team')
        _url(source['url'], team, kind)
        if source['url'] in urls:
            raise ValueError('Duplicate availability source URL')
        urls.add(source['url'])
        if not _utc(source['started_at']) <= _utc(source['captured_at']) <= now:
            raise ValueError('Availability source timestamps are out of order')
        record = {k: v for k, v in source.items() if k != 'body'}
        if 'error' not in source:
            _url(source['final_url'], team, kind)
            if source['status'] != 200 or not isinstance(source.get('body'), bytes):
                raise ValueError('Availability source needs HTTP 200 and raw bytes')
            raw = source['body']
            if ('sha256' in source and source['sha256'] != _sha(raw)) or ('bytes' in source and source['bytes'] != len(raw)):
                raise ValueError('Availability source hash or size differs')
            record.update(sha256=_sha(raw), bytes=len(raw))
        metadata.append(record)
        admitted.append((source, record))
    output = {}
    for game in games:
        teams = {}
        for team in (game['away'], game['home']):
            observations, errors, final_lists = [], [], []
            report_status = 'UNKNOWN'
            for source, record in admitted:
                if source.get('team') not in (None, team):
                    continue
                if 'error' in source:
                    errors.append(source['error'])
                    continue
                if source['kind'] in ('team_news','league_news'):
                    continue
                try:
                    if source['kind'] == 'official_report':
                        text = source['body'].decode('utf-8')
                        title = re.search(r'<title>(.*?)</title>', text, re.S | re.I)
                        if not title or f'Week {game["week"]} of the {game["season"]} Season' not in html.unescape(title[1]):
                            raise ValueError('Official injury report season/week differs')
                        tables = injury_tables(text)
                        label = TEAM_NAMES[team].split()[-1]
                        if label not in tables:
                            continue
                        report_status = 'VERIFIED_REPORT'
                        for row in tables[label]:
                            observations.append(dict(name=row['player_name'], position=row['position'],
                                status=row['game_status'].upper() or 'NO_GAME_DESIGNATION', injury=row['injury'],
                                practice_status=row['practice_status'], source_kind=source['kind'],
                                source_url=source['url'], captured_at=source['captured_at'], published_at=None,
                                source_sha256=record['sha256']))
                    else:
                        parsed = parse_final_inactives(source['body'], game, team, source['captured_at'], parser_version=parser_version)
                        final_lists.append((parsed, source, record))
                except (KeyError, TypeError, UnicodeError, ValueError) as error:
                    errors.append(str(error))
            final_status = 'UNKNOWN'
            if final_lists:
                parsed, source, record = max(final_lists, key=lambda value: _utc(value[0]['modified_at']))
                final_status = 'PARTIAL' if parsed['unparsed_lines'] else 'VERIFIED_LIST'
                errors.extend('Unparsed inactive-list line: ' + line for line in parsed['unparsed_lines'])
                observations.extend(dict(row, source_kind=source['kind'], source_url=source['url'],
                    captured_at=source['captured_at'], published_at=parsed['published_at'], source_sha256=record['sha256'])
                    for row in parsed['observations'])
            for row in observations:
                gsis = names[team].get(_normalize_player_name(row['name']))
                roster_row = indexed.get(gsis)
                conflict = roster_row is not None and ((row['position'] == 'QB') != (roster_row['position'] == 'QB'))
                row['gsis_id'] = None if conflict else gsis
                row['identity_status'] = 'POSITION_CONFLICT' if conflict else 'RESOLVED' if gsis else 'UNRESOLVED'
                if row['identity_status'] != 'RESOLVED':
                    if row['source_kind'] == 'official_report':
                        report_status = 'PARTIAL'
                    else:
                        final_status = 'PARTIAL'
            observed = [(row['source_url'], row['source_kind'], row['gsis_id'] or _normalize_player_name(row['name']))
                        for row in observations]
            if len(observed) != len(set(observed)):
                raise ValueError('Duplicate official player observation identity')
            statuses = [o['status'] for o in observations if o['gsis_id'] == expected_qbs[team]]
            qb_status = next((s for s in ('EMERGENCY_QB', 'INACTIVE', 'OUT', 'DOUBTFUL', 'QUESTIONABLE') if s in statuses), 'UNKNOWN')
            teams[team] = dict(report_status=report_status, final_inactives_status=final_status,
                               expected_qb_gsis_id=expected_qbs[team], expected_qb_status=qb_status,
                               observations=observations, source_errors=errors)
        blocked = [f'{team}: {indexed[expected_qbs[team]]["full_name"]} is {row["expected_qb_status"]}'
                   for team, row in teams.items() if row['expected_qb_status'] in UNAVAILABLE]
        output[game['game_id']] = dict(**{k:game[k] for k in ('game_id','season','week','game_type','home','away','kickoff','lock_at')},
            checked_at=now.isoformat(), teams=teams,
            qb_gate='BLOCKED_EXPECTED_QB_UNAVAILABLE' if blocked else 'CONDITIONAL',
            blocked_reason='Expected QB unavailable: ' + '; '.join(blocked) if blocked else None,
            summary='; '.join(f'{team}: official report {row["report_status"]}, final inactives {row["final_inactives_status"]}' for team,row in teams.items()))
    result = dict(schema_version=1, checked_at=now.isoformat(), games=output, sources=metadata,
                policy='Official dated context only. Missing reports or inactive-list names do not establish health. Non-QB numerical adjustments are not applied. Expected quarterback must play.')
    if parser_version == 2:
        result.update(purpose=purpose,parser_version=parser_version)
    return result


def _fetch(url):
    with urlopen(Request(url, headers={'User-Agent':'PGO-Availability/1.0'}), timeout=20) as response:
        raw = response.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError('Official source exceeds the capture size limit')
        return dict(body=raw, status=response.status, final_url=response.url)


def _write(path, raw):
    with path.open('xb') as handle:
        handle.write(raw)


def capture_availability(games, roster, expected_qbs, output, *, purpose='forecast', now=None, fetch=None):
    """Capture official reports once and discover bounded club inactive articles."""
    games, roster, expected_qbs = list(games), list(roster), dict(expected_qbs)
    _inputs(games, roster, expected_qbs, _clock(now), purpose)
    teams={t for g in games for t in (g['home'],g['away'])}
    games=[{k:g[k] for k in ('game_id','season','week','game_type','home','away','kickoff','lock_at')} for g in games]
    fields=('team','gsis_id','full_name','first_name','football_name','last_name','position','status')
    roster=[{k:r[k] for k in fields if k in r} for r in roster if normalize_team(r['team']) in teams]
    expected_qbs={t:expected_qbs[t] for t in teams}
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=False)
    (directory / 'raw').mkdir()
    fetch = fetch or _fetch
    source_rows = []
    def capture(spec):
        kind, team, url = spec
        started = _clock(now).isoformat()
        row = dict(kind=kind, team=team, url=url, started_at=started)
        try:
            value = fetch(_url(url, team, kind))
            _url(value['final_url'], team, kind)
            if value['status'] != 200 or not isinstance(value['body'], bytes):
                raise ValueError('Official source did not return HTTP 200/raw bytes')
            row.update({k:value[k] for k in ('body','status','final_url')})
        except Exception as error:
            row['error'] = f'{type(error).__name__}: {error}'
        row['captured_at'] = _clock(now).isoformat()
        return row
    teams = sorted({t for game in games if _utc(game['kickoff']) - _clock(now) <= timedelta(hours=24)
                    for t in (game['home'], game['away'])})
    specs = [('official_report', None, REPORT_URL)] + [('team_news',t,'https://www.'+TEAM_DOMAINS[t]+'/news/') for t in teams]
    if teams:
        specs.append(('league_news',None,NFL_NEWS_URL))
    with ThreadPoolExecutor(max_workers=4) as pool:
        source_rows.extend(pool.map(capture, specs))
    links = []
    for source in source_rows:
        if source['kind'] not in ('team_news','league_news') or 'error' in source:
            continue
        seen = set(); matched_counts = {g['game_id']:0 for g in games}
        for href, title in _Page(source['body'].decode('utf-8', errors='replace')).links:
            if not re.search(r'\binactive(?:s)?\b', title + ' ' + href, re.I):
                continue
            url = urljoin(source['url'], href)
            matched = [g for g in games if _matches_matchup(title+' '+urlsplit(url).path.replace('-',' '),g)]
            if source['kind'] == 'league_news' and not any(matched_counts[g['game_id']]<4 for g in matched):
                continue
            try:
                _url(url, source['team'], 'official_inactives')
            except ValueError:
                continue
            if url not in seen:
                seen.add(url)
                links.append(('official_inactives',source['team'],url))
                for game in matched:
                    matched_counts[game['game_id']] += 1
            if source['kind'] == 'team_news' and len(seen) == 4:
                break
    with ThreadPoolExecutor(max_workers=4) as pool:
        source_rows.extend(pool.map(capture, links))
    try:
        for index, source in enumerate(source_rows):
            if 'body' in source:
                source['file'] = f'raw/{index:03d}.html.gz'
                _write(directory/source['file'], gzip.compress(source['body'],mtime=0))
        checked = _clock(now).isoformat()
        result = build_availability(games, roster, expected_qbs, source_rows, checked_at=checked, purpose=purpose, parser_version=2)
        inputs = dict(games=games, roster=roster, expected_qbs=expected_qbs, purpose=purpose, parser_version=2)
        _write(directory/'inputs.json.gz',gzip.compress(_json(inputs),mtime=0))
        _write(directory/'capture.json',_json(dict(checked_at=checked,sources=result['sources'])))
        _write(directory/'availability.json',_json(result))
        members = [dict(file=p.relative_to(directory).as_posix(),sha256=_sha(p.read_bytes()),bytes=p.stat().st_size)
                   for p in sorted(directory.rglob('*')) if p.is_file()]
        _write(directory/'manifest.json',_json(dict(schema_version=1,checked_at=checked,members=members)))
        _inputs(games, roster, expected_qbs, _clock(now), purpose)
        return result
    except Exception as error:
        _write(directory/'failure.json',_json(dict(error=f'{type(error).__name__}: {error}',failed_at=_clock(now).isoformat())))
        raise


def _load_availability(directory):
    directory = Path(directory)
    if (directory/'failure.json').exists():
        raise ValueError('Availability capture failed; do not use its partial output')
    manifest = json.loads((directory/'manifest.json').read_bytes())
    if manifest.get('schema_version') != 1:
        raise ValueError('Availability manifest schema differs')
    payloads = {}
    for member in manifest['members']:
        name = member['file']
        if not isinstance(name,str) or any(c in name for c in ('\\',':','\x00')) or PurePosixPath(name).is_absolute() or any(p in ('','.','..') for p in name.split('/')):
            raise ValueError('Invalid availability package member')
        path = directory/name
        if (name in payloads or not path.resolve().is_relative_to(directory.resolve()) or path.is_symlink()
                or any(p.is_symlink() for p in path.parents if p != directory.parent)):
            raise ValueError('Duplicate or symlinked availability member')
        raw = path.read_bytes()
        if len(raw) != member['bytes'] or _sha(raw) != member['sha256']:
            raise ValueError('Availability member hash or size differs')
        payloads[name] = raw
    input_file='inputs.json.gz' if 'inputs.json.gz' in payloads else 'inputs.json'
    inputs = json.loads(gzip.decompress(payloads[input_file]) if input_file.endswith('.gz') else payloads[input_file])
    inputs.setdefault('purpose','forecast')
    inputs.setdefault('parser_version',1)
    capture = json.loads(payloads['capture.json'])
    sources = [dict(s,body=gzip.decompress(payloads[s['file']]) if s['file'].endswith('.gz') else payloads[s['file']]) if 'file' in s else dict(s) for s in capture['sources']]
    if set(payloads) != {input_file,'capture.json','availability.json'} | {s['file'] for s in sources if 'file' in s}:
        raise ValueError('Availability package member inventory differs')
    replay = build_availability(**inputs,sources=sources,checked_at=capture['checked_at'])
    if replay != json.loads(payloads['availability.json']) or replay['checked_at'] != manifest['checked_at']:
        raise ValueError('Availability replay differs from saved output')
    return replay


def load_availability(directory):
    """Verify all package members and replay, raising ValueError on invalid data."""
    try:
        return _load_availability(directory)
    except (KeyError, TypeError, OSError) as error:
        raise ValueError('Invalid availability package member or schema') from error
