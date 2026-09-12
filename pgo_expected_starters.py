"""Reviewed, game-specific starter announcements replayed from archived club news."""
import base64
import copy
from datetime import timedelta
import json
from pathlib import Path
import re

from pgo_season import IDENTITY, identity, require, sha, utc
from pgo_season_availability import _Page, _matches_matchup, _url
from pgo_season_rollover import source_bytes
from pgo_sources import CURRENT_TEAMS, normalize_team

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT/'data/pgo_starter_announcements.json'


def _primary_article(raw):
    """Return the unique JSON-LD primary article from exact response bytes."""
    articles = []
    for script in _Page(raw.decode('utf-8').split('<article', 1)[0]).scripts:
        value = json.loads(script)
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, dict) and item.get('@type') in ('NewsArticle','Article') and item.get('articleBody'):
                articles.append(item)
    require(len(articles) == 1, 'No unique primary starter article')
    return articles[0]


def _announcement(game, source, root, checked_at):
    require(type(game['season']) is int and game['season'] == 2026 and game['game_type'] == 'REG'
            and type(game['week']) is int and 1 <= game['week'] <= 18
            and game['home'] in CURRENT_TEAMS and game['away'] in CURRENT_TEAMS
            and game['home'] != game['away'], 'Invalid starter announcement game')
    parts = game['game_id'].split('_')
    require(len(parts) == 4 and parts[:2] == [str(game['season']), f"{game['week']:02d}"]
            and normalize_team(parts[2]) == game['away'] and normalize_team(parts[3]) == game['home'],
            'Starter announcement game identity differs')
    checked, kickoff = utc(checked_at), utc(game['kickoff'])
    cutoff = kickoff-timedelta(minutes=60)
    require(checked < cutoff and utc(game.get('lock_at', cutoff)) == cutoff,
            'Starter announcement must be issued before T-60')
    require(isinstance(source, dict) and re.fullmatch(r'[0-9a-f]{64}', source['sha256'])
            and source['path'] == 'source-archive/'+source['sha256']+'.json', 'Invalid starter source reference')
    record = json.loads(source_bytes(root, source, checked_at))
    require(type(record['schema_version']) is int and record['schema_version'] == 1
            and record['kind'] == 'official_starter_announcement'
            and type(record['status']) is int and record['status'] == 200, 'Invalid starter source envelope')
    decision = record['decision']; team = decision['team']
    require(team in (game['home'], game['away']) and set(decision['game']) == set(IDENTITY)
            and type(decision['game']['season']) is int and type(decision['game']['week']) is int
            and identity(decision['game'], game), 'Starter announcement is for a different game or team')
    require(isinstance(decision['gsis_id'], str) and re.fullmatch(r'00-\d{7}', decision['gsis_id'])
            and isinstance(decision['full_name'], str) and decision['full_name'].strip(), 'Invalid starter player identity')
    require(source['url'] == record['url'] == record['final_url'], 'Starter source URL or redirect differs')
    _url(record['url'], team, 'team_news')
    require(source['captured_at'] == record['captured_at'], 'Starter source capture clock differs')
    published, modified, captured, reviewed = (utc(record[key]) for key in
                                              ('published_at','modified_at','captured_at','reviewed_at'))
    require(kickoff-timedelta(days=7) <= published <= modified <= captured <= reviewed <= checked
            and utc(record['started_at']) <= captured, 'Starter source publication, capture or review clock differs')
    require(isinstance(record['body_base64'], str), 'Invalid starter HTML encoding')
    raw = base64.b64decode(record['body_base64'], validate=True)
    require(type(record['raw_bytes']) is int and len(raw) == record['raw_bytes'] > 0
            and sha(raw) == record['raw_sha256'], 'Starter HTML bytes differ')
    article = _primary_article(raw); body = article['articleBody']; statement = decision['statement']
    require(isinstance(body, str) and isinstance(statement, str) and statement
            and decision['full_name'] in statement and statement in body,
            'Reviewed starter statement is absent from the primary article')
    text = str(article.get('headline', ''))+'\n'+body
    require(_matches_matchup(text, game), 'Starter article matchup differs')
    require(all(int(week) == game['week'] for week in re.findall(r'\bweek\s+(\d+)\b', text, re.I)),
            'Starter article identifies a different week')
    require(article['datePublished'] == record['published_at']
            and article.get('dateModified', article['datePublished']) == record['modified_at'],
            'Starter article publication or modification differs')
    return decision


def select_player(roster, decision, game):
    """Resolve one current ACT quarterback and detach the selected roster row."""
    rows = [row for row in roster if row.get('gsis_id') == decision['gsis_id']]
    require(len(rows) == 1 and normalize_team(rows[0]['team']) == decision['team']
            and str(rows[0]['season']) == str(game['season']) and rows[0]['status'] == 'ACT'
            and rows[0]['position'] == 'QB' and rows[0]['full_name'] == decision['full_name'],
            'Announced starter requires one matching current ACT quarterback')
    return copy.deepcopy(rows[0])


def apply(selected, roster, games, root, checked_at):
    """Return a detached selection plus source annotations for matching games only."""
    chosen = copy.deepcopy(selected)
    if not CONFIG.exists():
        return chosen, {}
    try:
        config = json.loads(CONFIG.read_bytes())
        require(type(config['schema_version']) is int and config['schema_version'] == 1
                and isinstance(config['announcements'], list), 'Invalid starter announcement configuration')
        indexed = {game['game_id']:game for game in games}
        applicable = [rule for rule in config['announcements'] if rule['game_id'] in indexed]
        if not applicable:
            return chosen, {}
        require(len(indexed) == len(games), 'Duplicate starter announcement input game')
        annotations = {}; seen = set()
        for rule in applicable:
            game = indexed[rule['game_id']]; decision = _announcement(game, rule['source'], root, checked_at)
            team = decision['team']; key = (game['game_id'], team)
            require(key not in seen, 'Duplicate starter announcement for game and team'); seen.add(key)
            chosen[team] = select_player(roster, decision, game)
            annotations.setdefault(game['game_id'], []).append(dict(
                team=team, gsis_id=decision['gsis_id'], full_name=decision['full_name'], source=copy.deepcopy(rule['source'])))
        require(set(chosen) == set(CURRENT_TEAMS), 'Expected starters must cover all 32 teams')
        ids = [row['gsis_id'] for row in chosen.values()]
        require(all(isinstance(pid, str) and re.fullmatch(r'00-\d{7}', pid) for pid in ids)
                and len(set(ids)) == 32 and all(normalize_team(row['team']) == team for team, row in chosen.items()),
                'Expected starter identities are missing, duplicated or assigned to another team')
        return chosen, annotations
    except (KeyError, TypeError, AttributeError, OverflowError) as error:
        raise ValueError('Invalid starter announcement schema') from error


def verify(game, annotations, root):
    """Verify issued annotations against their original evidence, never current config."""
    require(isinstance(annotations, list), 'Invalid starter annotations')
    if not annotations:
        return
    try:
        issued = utc(game['issued_at']); inputs = utc(game.get('inputs_as_of', game['issued_at']))
        require(inputs <= issued < utc(game['kickoff'])-timedelta(minutes=60),
                'Starter input or issue clock is invalid or late')
        seen = set()
        for annotation in annotations:
            decision = _announcement(game, annotation['source'], root, inputs)
            team = decision['team']
            require(team not in seen and all(annotation[key] == decision[key] for key in ('team','gsis_id','full_name')),
                    'Saved starter annotation identity differs or is duplicated'); seen.add(team)
            require(game['expected_qbs'][team] == decision['full_name'], 'Saved forecast quarterback differs from announcement')
            availability = (game.get('availability') or {}).get('teams', {}).get(team, {})
            require('expected_qb_gsis_id' not in availability or availability['expected_qb_gsis_id'] == decision['gsis_id'],
                    'Saved availability quarterback differs from announcement')
    except (KeyError, TypeError, AttributeError, OverflowError) as error:
        raise ValueError('Invalid saved starter announcement schema') from error
