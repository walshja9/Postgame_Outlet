"""Pure presentation of verified season state; never fetches, fits, issues or grades."""
from collections import Counter
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
import html
import math
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

import pgo_current_board as board
from pgo_season import utc

GRADES = {'W': 'W', 'L': 'L', 'T': 'T', 'PENDING': 'Pending', 'NO_PICK': 'No pick'}
FORECAST_STATES = {'DRAFT', 'LOCKED', 'BLOCKED', 'FINAL'}
WEEK_STATES = {'UPCOMING', 'IN_PROGRESS', 'COMPLETE', 'BLOCKED'}
SEASON_HEADERS = ('Matchup', 'Winner pick', 'Predicted score', 'Winner and spread checks',
                  'Final score', 'Confidence allocation', 'Forecast status and times')


def _text(value):
    return html.escape(str(value), quote=True)


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Season display requires finite numeric values')
    return value


def _integer(value):
    if type(value) is not int or value < 0:
        raise ValueError('Season display requires nonnegative integer counts')
    return value


def _time(value, *, clock_only=False):
    if not value: return 'Unavailable'
    if clock_only:
        label = utc(value).astimezone(ZoneInfo('America/New_York')).strftime('%I:%M %p %Z').lstrip('0')
        return f'<time datetime="{_text(value)}">{label}</time>'
    return board._time(value)


def _check_time(value, reference, minutes=45, until=None, *, ended_label=None):
    if not value:
        return 'No verified check saved'
    expired = until and utc(reference) >= utc(until)
    status = ('Check time ahead of this clock' if utc(value)>utc(reference) else (ended_label or 'Updates closed at lock') if expired else
              'Update overdue' if (utc(reference)-utc(value)).total_seconds() > minutes*60 else 'Recently checked')
    end = f' data-freshness-until="{_text(until)}"' if until else ''
    if ended_label: end += f' data-freshness-ended-label="{_text(ended_label)}"'
    return (_time(value) + f'<span class="freshness-status" data-freshness-at="{_text(value)}" '
            f'data-freshness-minutes="{minutes}" data-overdue="{str(status == "Update overdue").lower()}"{end}>{status}</span>')


def _freshness(state):
    checked = state['checked_at']
    rankings = state.get('rankings') or {}
    score_checks = [r['captured_at'] for r in state.get('source_captures', [])
                    if '/scoreboard?' in r.get('url','') and r.get('captured_at')]
    upcoming = [g for w in state['weeks'] for g in w['games']
                if 3600 < (utc(g['kickoff'])-utc(checked)).total_seconds() <= 86400]
    available = [g.get('availability',{}).get('checked_at') for g in upcoming]
    availability = ('No unlocked games within the next 24 hours. Checks begin in that window.' if not upcoming else
                    _check_time(min(available,key=utc),checked,30,max((g['lock_at'] for g in upcoming),key=utc))
                    if all(available) else 'Some games in the check window have no verified check saved')
    rows = [('Rankings calculated', _time(rankings.get('generated_at'))),
            ('Forecast availability checked', availability),
            ('Results checked', _check_time(min(score_checks,key=utc) if score_checks else None,checked)),
            ('Automation checked', _check_time(checked,checked))]
    return ('<dl class="season-freshness season-checks">'
            + ''.join(f'<div><dt>{title}</dt><dd>{value}</dd></div>' for title,value in rows) + '</dl>')


def _absences(game, compact=False):
    availability = game.get('availability') or {}
    teams = availability.get('teams', {})
    rows, seen = [], set()
    labels = {'OUT':'Out', 'INACTIVE':'Inactive', 'EMERGENCY_QB':'Emergency third QB',
              'DOUBTFUL':'Doubtful', 'QUESTIONABLE':'Questionable'}
    for team in (game['away'],game['home']):
        observations = teams.get(team,{}).get('observations',[])
        final_ids = {item.get('gsis_id') or item.get('name') for item in observations
                     if item.get('status') in ('INACTIVE','EMERGENCY_QB')}
        for item in observations:
            status = labels.get(item.get('status'))
            key = (team,item.get('gsis_id') or item.get('name'),status)
            if not status or key in seen: continue
            if (item.get('status') in ('QUESTIONABLE','DOUBTFUL')
                    and teams[team].get('final_inactives_status') == 'VERIFIED_LIST'
                    and (item.get('gsis_id') or item.get('name')) not in final_ids):
                status = 'Earlier report: ' + status + '; not on final inactive list'
            seen.add(key)
            identity = ' (identity unconfirmed)' if item.get('identity_status') not in (None,'RESOLVED') else ''
            rows.append(f'<li>{_text(team)} &middot; {_text(item["name"])} ({_text(item.get("position","Unknown role"))}): {status}{identity}</li>')
    if compact:
        return ('<p><strong>Out or uncertain:</strong></p><ul class="game-day-absences">' + ''.join(rows[:3]) + '</ul>'
                + (f'<p>{len(rows)-3} more in availability details.</p>' if len(rows)>3 else '')) if rows else ''
    notes = '<ul class="game-day-absences">' + ''.join(rows) + '</ul>' if rows else '<p>No named out or uncertain players in this saved report; this is not a clean bill of health.</p>'
    if any(teams.get(t,{}).get('final_inactives_status') != 'VERIFIED_LIST' for t in (game['away'],game['home'])):
        notes += '<p>Final inactive lists are not fully verified.</p>'
    sources = sorted({item['source_url'] for team in teams.values() for item in team.get('observations',[]) if item.get('source_url')})
    notes += _sources([{'href':url,'label':'Official availability source'} for url in sources])
    return notes


def _inactive_watch(state):
    from pgo_season import availability_watch
    watch = availability_watch(state)
    if not watch['games'] and not watch.get('blocked_reason'):
        return ''
    rows = []
    for game in watch['games']:
        missing = ', '.join(game['missing_teams'])
        if game['status'] == 'MISSING':
            note = 'Final inactive lists missing: ' + missing
        elif game['status'] == 'STALE':
            note = 'Final inactive check was overdue' + ('; lists missing: ' + missing if missing else '')
        elif game['status'] == 'AWAITING':
            note = 'Awaiting final inactive lists: ' + missing
        else:
            note = 'Final inactive lists verified for both teams'
        rows.append(f'<li><strong>{_text(game["away"])} @ {_text(game["home"])}: {_text(note)}.</strong> '
                    f'Last observation: {_check_time(game.get("checked_at"),watch["checked_at"],10,game["kickoff"],ended_label="Kickoff reached; final list status shown above")}'
                    + (' Prediction is already locked.' if game['after_lock'] else '') + '</li>')
    blocked = (f'<p><strong>Availability update needs review:</strong> {_text(watch["blocked_reason"])}</p>'
               if watch.get('blocked_reason') else '')
    return ('<aside class="notice" id="season-inactive-watch"><h3>Final inactive watch</h3>'
            f'<p>Watch assessed {_time(watch["checked_at"])}.</p>'
            + blocked + '<ul>' + ''.join(rows) + '</ul>'
            '<p>Later availability updates are reader context. They do not rewrite locked predictions or grades.</p></aside>')


def _latest_availability(game, context, *, compact=False):
    if not context:
        return ''
    captured = context.get('checked_at')
    timing = ''
    if captured and utc(captured) >= utc(game['kickoff']):
        timing = 'This update was observed after kickoff.'
    elif captured and utc(captured) >= utc(game['lock_at']):
        timing = 'This update was observed after prediction lock.'
    current = dict(game, availability=context)
    body = (_absences(current) + '<p>This is separate from the saved forecast availability and expected quarterbacks. '
            'It does not change the original prediction or its grade.</p>')
    if compact:
        missing = any(context.get('teams',{}).get(team,{}).get('final_inactives_status') != 'VERIFIED_LIST'
                      for team in (game['away'],game['home']))
        body = (('<p><strong>Final inactive lists are not fully verified.</strong></p>' if missing else '')
                + _absences(current, True)
                + f'<details data-view-key="game-day-latest-{_text(game["game_id"])}">'
                '<summary>All latest absences and sources</summary>' + body + '</details>')
    return ('<div class="forecast-reason-block"><h3>Latest availability update</h3>'
            f'<p>Observed {_time(captured)}. <strong>{timing}</strong></p>' + body + '</div>')


def _game_day(state):
    eastern = ZoneInfo('America/New_York')
    day = utc(state['checked_at']).astimezone(eastern).date()
    games = sorted((g for w in state['weeks'] for g in w['games']),key=lambda g:(utc(g['kickoff']),g['game_id']))
    today = [g for g in games if utc(g['kickoff']).astimezone(eastern).date() == day]
    cards = []
    ats_games = {g['game_id']:g for g in (state.get('ats') or {}).get('games',[])}
    for game in today:
        context = (state.get('availability_context') or {}).get(game['game_id'])
        key = _text(game['game_id']); confidence = game.get('confidence') or {}
        pick = ('Pick withheld' if game.get('blocked_reason') or game['forecast_status']=='BLOCKED' else
                f'PGO winner pick: {_text(game["pick"])}' if game.get('pick') else 'No model edge')
        probability = confidence.get('win_probability')
        chance = ''
        if game.get('pick') and not game.get('blocked_reason') and game['forecast_status']!='BLOCKED' and probability is not None:
            if not 0 <= _number(probability) <= 1: raise ValueError('Invalid saved win probability')
            chance = ('<p>Probability added after lock; excluded from pregame accuracy.</p>' if confidence.get('added_after_lock') else
                      f'<p class="game-day-chance">{probability:.1%} win chance</p>')
        lines = ''
        if state.get('ats'):
            quote = ats_games.get(game['game_id'])
            if quote:
                handicap = _number(quote['home_handicap'])
                label = f'{_text(game["home"])} {handicap:+g}'
                lines = f'<p>Saved sportsbook line: <strong>{label}</strong> (via ESPN). '
                if quote.get('status')=='STALE' or quote.get('stale_reason'):
                    lines += 'Comparison needs a fresh check. '
            else:
                lines = '<p>Sportsbook line unavailable. '
            lines += f'<a href="#season-ats" data-view-key="game-day-ats-{key}">PGO projected line and coverage checks</a></p>'
        result = game.get('result')
        status = ('Final: ' + f'{_text(game["away"])} {_integer(result["away_score"])}, {_text(game["home"])} {_integer(result["home_score"])}'
                  if result else '<span data-weekly-cutoff="' + _text(game['lock_at']) + '">' + ('Locked' if utc(state['checked_at'])>=utc(game['lock_at']) else 'Draft') + '</span>'
                  if game['forecast_status']!='BLOCKED' and not game.get('blocked_reason') else 'Withheld')
        cards.append(f'<article class="game-day-card"><div><h4>{_text(game["away"])} @ {_text(game["home"])}</h4>'
                     f'<p class="game-day-pick">{pick}</p>{chance}{lines}<p>{status}</p>'
                     f'<dl class="game-day-times"><div><dt>Kickoff</dt><dd>{_time(game["kickoff"],clock_only=True)}</dd></div>'
                     f'<div><dt>Prediction lock</dt><dd>{_time(game["lock_at"],clock_only=True)}</dd></div></dl></div><div>{_latest_availability(game,context,compact=True) if context else _absences(game,True)}'
                     f'<details data-view-key="game-day-availability-{key}"><summary>Saved forecast availability</summary>{_absences(game)}'
                     f'<p>{_check_time((game.get("availability") or {}).get("checked_at"),state["checked_at"],30,game["lock_at"])}</p>'
                     '<p>Non-QB absences are context; their impact is not fitted into this pick.</p></details>'
                     f'<a class="game-day-link" href="#season-game-{key}" data-view-key="game-day-link-{key}">Score estimate and explanation</a></div></article>')
    empty = '<p>No games on this date.'
    next_game = next((g for g in games if utc(g['kickoff']).astimezone(eastern).date()>day),None)
    if next_game and not cards:
        week = _integer(next_game['week'])
        count = sum(len(w['games']) for w in state['weeks'] if w['week'] == week)
        slate = f'See all {count} Week {week} games' if count != 1 else f'See the Week {week} game'
        empty += (f' Next saved game: <a href="#season-game-{_text(next_game["game_id"])}">'
                  f'{_text(next_game["away"])} @ {_text(next_game["home"])}</a> &middot; {_time(next_game["kickoff"])}. '
                  f'<a href="#season-week-{week}">{slate}</a>.')
        checked = utc(state['checked_at'])
        lock = utc(next_game['lock_at'])
        starts = utc(next_game['kickoff']) - timedelta(hours=24)
        empty += f'</p><p>Prediction {"locked" if checked >= lock else "lock"}: {_time(next_game["lock_at"])}. '
        if checked >= lock:
            empty += 'Later availability news is shown separately from the saved pick.'
        elif checked < starts:
            empty += f'Availability checks become due {_time(starts.isoformat())}.'
        else:
            empty += ('Availability-check window is open. Last saved forecast availability check: '
                      + _check_time((next_game.get('availability') or {}).get('checked_at'), state['checked_at'], 30, next_game['lock_at']) + '.')
    return (f'<h3 id="season-game-day">Game day &middot; {day.strftime("%B %d").replace(" 0"," ")} (Eastern)</h3>'
            + ('<div class="game-day-grid">' + ''.join(cards) + '</div>' if cards else empty+'</p>'))


def _sources(sources):
    rows = []
    for source in sources:
        href = source['href']
        decoded = unquote(href)
        parsed = urlsplit(decoded)
        if (not href or any(ord(c) < 32 for c in decoded) or '\\' in decoded
                or decoded.startswith('//') or '..' in parsed.path.split('/')
                or (parsed.scheme and (parsed.scheme != 'https' or not parsed.netloc))
                or (not parsed.scheme and parsed.netloc)):
            raise ValueError('Season sources require safe relative or HTTPS links')
        rows.append(f'<li><a href="{_text(href)}">{_text(source.get("label", href))}</a></li>')
    return '<ul>' + ''.join(rows) + '</ul>' if rows else ''


def _rank_comparison(snapshot, mccabe):
    if mccabe is None:
        return ''
    rows = mccabe['rows']
    codes = {team['team'] for team in snapshot['teams']}
    if (len(rows) != 32 or {row['abbr'] for row in rows} != codes
            or sorted(_integer(row['rank']) for row in rows) != list(range(1,33))):
        raise ValueError('McCabe comparison requires all 32 ranked teams')
    ranks = {row['abbr']: row['rank'] for row in rows}
    differences = [(team, ranks[team['team']]-team['rank']) for team in snapshot['teams']]
    def label(gap):
        return ('Same rank' if gap == 0 else
                f'PGO {abs(gap)} {"place" if abs(gap)==1 else "places"} {"higher" if gap>0 else "lower"}')
    largest = sorted(differences,key=lambda item:(-abs(item[1]),item[0]['team']))[:3]
    overview = '; '.join(f'{_text(team["team"])}: {label(gap)}' for team,gap in largest if gap)
    body = ''.join(f'<tr data-rank-compare="{_text(team["team"])}"><th scope="row">{_text(team["team"])}</th>'
                   f'<td>{team["rank"]}</td><td>{ranks[team["team"]]}</td><td>{label(gap)}</td></tr>'
                   for team,gap in sorted(differences,key=lambda item:item[0]['rank']))
    return ('<details class="model-update-evidence" id="season-rank-comparison" data-view-key="rank-comparison">'
            '<summary>Current PGO vs. McCabe rankings</summary>'
            f'<p>PGO edition: {_time(snapshot["generated_at"])}. McCabe source: {_time(mccabe["as_of"])}.</p>'
            '<p>This compares rank positions, not points. Each board uses its own method and rating scale.</p>'
            f'<p><strong>Largest rank gaps:</strong> {overview or "Both boards have the same order"}.</p>'
            '<div class="table-shell"><table class="rank-comparison-table"><thead><tr>'
            '<th scope="col">Team</th><th scope="col">PGO</th><th scope="col">McCabe</th><th scope="col">Rank difference</th>'
            f'</tr></thead><tbody>{body}</tbody></table></div></details>')


def _rankings(snapshot, mccabe=None):
    if snapshot is None:
        return '<p>Rankings unavailable.</p>'
    from pgo_forecast_lab import _rating_labels
    teams = sorted(snapshot['teams'], key=lambda row: row['rank'])
    codes = {row[0] for row in board.generate_site.TEAM.values()}
    if (len(teams) != 32 or {row['team'] for row in teams} != codes
            or [row['rank'] for row in teams] != list(range(1, 33))):
        raise ValueError('Season rankings require all 32 ranked team identities')
    labels = _rating_labels()
    plain = dict(pgo_v0='recent game results', passing_epa_per_play_for='passing performance',
                 passing_epa_per_play_against='pass defense', rushing_epa_per_play_for='rushing performance',
                 rushing_epa_per_play_against='run defense', sack_creation_rate='sacks made by the defense',
                 sack_avoidance_rate='avoiding sacks', takeaway_rate='winning turnovers',
                 giveaway_avoidance_rate='protecting the ball', qb_epa_per_dropback='quarterback passing history',
                 qb_cpoe='quarterback completion history', qb_log_dropbacks='amount of quarterback history',
                 qb_experience_prior='quarterback experience', qb_draft_prior='quarterback draft history')
    rows, explanations = [], []
    for team in teams:
        rating = _number(team['rating'])
        prior = team.get('prior_rank')
        if prior is not None and not 1 <= _integer(prior) <= 32:
            raise ValueError('Invalid previous rank')
        movement = 'First edition' if prior is None else ('Unchanged' if prior == team['rank'] else f'Up {prior-team["rank"]}' if prior > team['rank'] else f'Down {team["rank"]-prior}')
        code = _text(team['team'])
        rows.append(f'<tr data-season-team="{code}"><td class="pgo-rank">{team["rank"]}</td>'
            f'<th scope="row" class="pgo-team"><a href="#season-rating-{code}" data-view-key="rating-link-{code}">{board.team_identity(team["team"])}</a></th>'
            f'<td class="pgo-rating-value" data-value="{rating}">{rating:+.3f}</td><td>{movement}</td>'
            f'<td class="model-update-extra pgo-rating-scale">{board.rating_bar(rating)}</td>'
            f'<td class="model-update-extra">{_text(team["qb_name"])}</td></tr>')
        terms = team.get('contributions', {})
        for value in terms.values(): _number(value)
        if terms and not math.isclose(math.fsum(terms.values()), rating, rel_tol=0, abs_tol=1e-8):
            raise ValueError('Season rating contributions do not reconcile')
        def drivers(positive):
            chosen = sorted(((name, value) for name, value in terms.items()
                             if (value > 0 if positive else value < 0)), key=lambda pair: -abs(pair[1]))[:3]
            return ', '.join(_text(plain.get(name, 'adjustments for missing information' if name.endswith('_missing')
                                else labels.get(name, name.replace('_', ' ')))) for name, _ in chosen) or 'None recorded'
        calculations = []
        for name, value in sorted(terms.items(), key=lambda pair:-abs(pair[1])):
            raw = team.get('features', {}).get(name.removesuffix('_missing'))
            shown = str(int(raw is None)) if name.endswith('_missing') else ('Unavailable' if raw is None else f'{_number(raw):.4g}')
            calculations.append(f'<tr><th scope="row">{_text(labels.get(name, name.replace("_", " ")))}</th>'
                                f'<td>{shown}</td><td>{value:+.3f}</td></tr>')
        calculations = ''.join(calculations)
        explanations.append(f'<details class="model-update-evidence rating-explanation" id="season-rating-{code}" data-view-key="rating-{code}">'
            f'<summary>#{team["rank"]} {code}: why this rating</summary>'
            f'<p>Expected quarterback: {_text(team["qb_name"])}.</p>'
            f'<p><strong>What lifts this rating:</strong> {drivers(True)}.</p>'
            f'<p><strong>What holds this rating back:</strong> {drivers(False)}.</p>'
            '<p>These are overlapping influences in the formula, not separate player-quality grades. '
            'Current non-QB injuries and backup quality are not numerical adjustments here.</p>'
            f'<details data-view-key="rating-calculation-{code}"><summary>Saved calculation</summary><div class="table-shell" data-view-key="rating-table-{code}"><table><thead><tr>'
            '<th>Input</th><th>Saved input value</th><th>Contribution to rating</th></tr></thead>'
            f'<tbody>{calculations}</tbody></table></div>'
            '<p>Input values use different scales and cannot be added together. The formula converts each into a contribution; '
            'those contributions sum to the displayed rating. EPA measures how a play changes expected scoring; '
            'completion percentage above expectation compares completions with the expected rate for those throws.</p>'
            f'<p>Edition: {_text(snapshot["edition"])}. Generated {_time(snapshot["generated_at"])}.</p></details></details>')
    if teams != sorted(teams, key=lambda row: (-row['rating'], row['team'])):
        raise ValueError('Season team ranks differ from saved rating order')
    history = utc(snapshot['history_through']).astimezone(ZoneInfo('America/New_York')).strftime('%B %d, %Y').replace(' 0',' ')
    movement_note = ('Rank change compares this edition with the previous saved ranking edition.' if any(t.get('prior_rank') is not None for t in teams)
                     else 'First saved ranking edition; rank movement starts with the next edition.')
    return (f'<h3 id="season-rankings">Current power rankings</h3><p>Ranking inputs captured {_time(snapshot["inputs_as_of"])}. '
            f'Includes completed games through {history}. This is the date of the latest included game, not a data-capture deadline. '
            f'{movement_note}</p>'
            '<label class="model-update-columns"><input type="checkbox" data-view-key="rating-columns"> Show rating scale and expected QB</label>'
            '<div class="table-shell" data-view-key="rankings-table"><table class="postseason-team-table"><thead><tr>'
            '<th>Rank</th><th>Team</th><th>PGO strength</th><th>Rank change</th>'
            '<th class="model-update-extra">Rating scale</th><th class="model-update-extra">Expected QB</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
            '<details class="model-update-evidence" data-view-key="rating-reasons"><summary>Why teams rank here</summary>'
            + ''.join(explanations) + '</details>' + _rank_comparison(snapshot,mccabe))


def _postgame_card(game, comparison):
    result = game.get('result')
    if result is None or game['forecast_status'] != 'FINAL' or game['grade'] == 'PENDING':
        return ''
    from pgo_ats_view import grade_label
    actual_margin = _integer(result['home_score'])-_integer(result['away_score'])
    actual_total = result['home_score']+result['away_score']
    winner = {'W':'Correct','L':'Incorrect','T':'Game tied','NO_PICK':'No pick'}[game['grade']]
    if game.get('pick'): winner = f'{_text(game["pick"])}: {winner}'
    ats = 'No saved sportsbook line'
    if comparison is not None:
        ats = grade_label(comparison.get('grade',{}).get('ats','UNAVAILABLE'),ats_choice=True)
        if comparison.get('ats_pick'):
            ats = f'{_text(comparison["ats_pick"])}: {ats}'
    margin = ('No saved estimate' if game.get('margin') is None else
              f'{abs(_number(game["margin"])-actual_margin):.1f} points')
    total = 'No saved estimate'
    if game.get('total') is not None:
        error = _number(game['total'])-actual_total
        total = f'{abs(error):.1f} points' + (' too high' if error>0 else ' too low' if error<0 else ' (exact)')
    items = [('Winner pick',winner),('ATS suggestion',ats),('Margin error',margin),('Scoring error',total)]
    key = _text(game['game_id'])
    return (f'<div class="postgame-card" role="group" aria-labelledby="recap-{key}">'
            f'<h4 id="recap-{key}">Result report card</h4><dl>'
            + ''.join(f'<div><dt>{title}</dt><dd>{value}</dd></div>' for title,value in items) + '</dl>'
            '<p>Errors compare the saved, unrounded estimates with the final score. Lower is better. '
            'ATS uses the saved sportsbook line.</p></div>')


def _game(game, week, comparison=None, availability_context=None):
    from pgo_forecast_lab import _spread, _projected_score
    if game['grade'] not in GRADES or game['forecast_status'] not in FORECAST_STATES:
        raise ValueError('Unknown season forecast or grade status')
    codes = {row[0] for row in board.generate_site.TEAM.values()}
    if game['home'] not in codes or game['away'] not in codes or game['home'] == game['away']:
        raise ValueError('Invalid season game teams')
    if game.get('pick') not in (None, game['home'], game['away']):
        raise ValueError('Pick must identify one of the game teams')
    home, away = _text(game['home']), _text(game['away'])
    game_id = _text(game['game_id'])
    scores = 'Forecast unavailable'
    calculation = 'No saved numerical forecast is available for this matchup.'
    explanation_steps = []
    favorite = 'No pick' if game.get('pick') is None else _text(game['pick'])
    if game.get('margin') is not None:
        margin, total, hp, ap = (_number(game[name]) for name in ('margin','total','home_points','away_points'))
        if not (math.isclose(hp,(total+margin)/2,abs_tol=1e-8) and math.isclose(ap,(total-margin)/2,abs_tol=1e-8)):
            raise ValueError('Season saved scores do not reconcile')
        whole = [Decimal(str(value)).quantize(Decimal('1'),rounding=ROUND_HALF_UP) for value in (ap,hp)]
        summary = f'About {whole[0]} points each' if whole[0] == whole[1] else f'{away} {whole[0]}, {home} {whole[1]}'
        scores = f'Predicted: {summary}<details data-view-key="score-{game_id}"><summary>Model averages</summary><p>{away} {_projected_score(ap)}, {home} {_projected_score(hp)}</p></details>'
        favorite += f'<br><small>Projected margin:<br>{_spread(game)}</small>'
        explanation = game.get('explanation')
        components = ''
        if explanation is not None:
            neutral, venue, rest = (_number(explanation[name]) for name in ('neutral_margin','home_adjustment','rest_adjustment'))
            if not math.isclose(math.fsum((neutral,venue,rest)),margin,rel_tol=0,abs_tol=1e-8):
                raise ValueError('Saved matchup explanation does not reconcile to its margin')
            explanation_steps.append('On a neutral field, neither team has a projected edge.' if neutral == 0 else
                                     'On a neutral field, PGO favors ' + _spread(dict(game,margin=neutral)) + '.')
            for label, adjustment in (('venue',venue),('rest',rest)):
                explanation_steps.append(f'No {label} adjustment.' if adjustment == 0 else
                                         f'The {label} adjustment favors ' + _spread(dict(game,margin=adjustment)) + '.')
            components = (f'Neutral matchup: {neutral:+.2f} points; Home/venue adjustment: {venue:+.2f} points; '
                          f'rest adjustment: {rest:+.2f} points. Positive values favor {home}. ')
            if 'home_rating' in explanation or 'away_rating' in explanation:
                home_rating, away_rating = (_number(explanation[name]) for name in ('home_rating','away_rating'))
                if not math.isclose(home_rating-away_rating,neutral,rel_tol=0,abs_tol=1e-8):
                    raise ValueError('Saved rating inputs do not reconcile to neutral matchup')
                components = (f'Ratings saved for this forecast: {home} {home_rating:+.3f}; {away} {away_rating:+.3f}. '
                              f'Rating inputs through {_time(explanation.get("rating_inputs_as_of"))}. ' + components)
        explanation_steps.append(f'Final projected edge: {_spread(game)}. Combined-points estimate: {total:.1f}.')
        calculation = (components + f'The saved model favors {_spread(game)}. Its combined-points estimate is {total:.1f}. '
                       f'Home average = (combined points + home lead) / 2 = {hp:.2f}; away average = '
                       f'(combined points - home lead) / 2 = {ap:.2f}. Rounded scores are not literal final-score predictions.')
        if game['forecast_status'] == 'BLOCKED' or game.get('blocked_reason'):
            scores = '<strong>Saved conditional estimate</strong><br>' + scores
            explanation_steps.insert(0,'This estimate is withheld as a pick until the blocking issue is resolved.')
            calculation = 'This estimate is withheld as a pick until the blocking issue is resolved. ' + calculation
    result = game.get('result')
    actual = 'Pending' if result is None else f'Final: {away} {_integer(result["away_score"])}, {home} {_integer(result["home_score"])}'
    outcomes = f'<strong>Winner:</strong> {GRADES[game["grade"]]}'
    if comparison is not None:
        from pgo_ats_view import grade_label
        if any(comparison.get(key) != game[key] for key in ('home','away')):
            raise ValueError('Saved comparison teams differ from the matchup')
        if any(comparison.get(key) != game.get(source) for key,source in
               (('pgo_margin','margin'),('pgo_issued_at','issued_at'),('source_edition','source_edition'),('su_pick','pick'))):
            outcomes += '<br><strong>Earlier saved comparison</strong>'
        for key,label,team in (('model_line','PGO line',comparison.get('su_pick')),
                               ('straight_up_ats','Winner vs sportsbook',comparison.get('su_pick')),
                               ('ats','ATS pick',comparison.get('ats_pick'))):
            value = comparison.get('grade',{}).get(key,'UNAVAILABLE')
            line = ''
            if team and value != 'UNAVAILABLE':
                if team not in (game['home'],game['away']):
                    raise ValueError('Saved comparison pick is outside the matchup')
                handicap = (-_number(comparison['pgo_margin']) if key == 'model_line' else
                            _number(comparison['home_handicap']))
                handicap = handicap if team == game['home'] else -handicap
                shown = f'{handicap:+.1f}' if key == 'model_line' else f'{handicap:+g}'
                line = f' ({_text(team)} {shown})'
            result_label = grade_label(value,ats_choice=key=='ats',model_line=key=='model_line')
            outcomes += f'<br><small>{label}{line}: {result_label}</small>'
        if comparison.get('stale_reason'):
            outcomes += '<br><small>Stale comparison; see saved details.</small>'
        outcomes += f'<br><a href="#season-ats-game-{game_id}" data-view-key="game-grades-{game_id}">Saved lines and grading details</a>'
    confidence = game.get('confidence')
    pool = 'Confidence unavailable'
    if confidence is not None:
        points = _integer(confidence['points'])
        probability, expected = confidence.get('win_probability'), confidence.get('expected_points')
        if points < 1 or (probability is not None and not 0 <= _number(probability) <= 1):
            raise ValueError('Invalid season confidence allocation')
        shown = 'Unavailable' if probability is None else f'{probability:.1%}'
        expected_text = 'Unavailable' if expected is None else f'{_number(expected):.2f}'
        earned = confidence.get('earned_points')
        earned_text = 'Pending' if earned is None else str(_integer(earned))
        if ((expected is not None and (probability is None or not math.isclose(expected,points*probability,rel_tol=0,abs_tol=1e-8)))
                or (earned is not None and earned > points)):
            raise ValueError('Season confidence points do not reconcile')
        pool = (f'{points} allocated pool points; win chance {shown}<br>'
                f'Expected pool points: {expected_text}<br>Earned pool points: {earned_text}')
        if confidence.get('added_after_lock'):
            pool += '<br><strong>Added after lock</strong>'
        elif confidence.get('added_after_lock') is None:
            pool += '<br><strong>Timing not recorded</strong>'
    availability = game.get('availability') or {}
    note = '' if availability.get('teams') else _text(availability.get('summary') or 'Availability not verified')
    reason = game.get('blocked_reason') or availability.get('blocked_reason')
    if reason: note += ('<br>' if note else '') + f'<strong>{_text(reason)}</strong>'
    note += ('<br>' if note else '') + 'Checked ' + _time(availability.get('checked_at'))
    provenance = ''
    if game.get('issued_at'):
        provenance += f'<p>Issued {_time(game["issued_at"])}; inputs through {_time(game.get("inputs_as_of"))}.</p>'
    if game.get('expected_qbs'):
        quarterbacks = '; '.join(f'{_text(team)}: {_text(game["expected_qbs"].get(team) or "Unavailable")}'
                                 for team in (game['away'],game['home']))
        provenance += f'<p>Expected quarterbacks saved with this forecast: {quarterbacks}.</p>'
    status = game['forecast_status']
    if status in ('DRAFT','LOCKED'):
        status = f'<span class="weekly-status" data-weekly-cutoff="{_text(game["lock_at"])}">{status.title()}</span>'
    values = (favorite, scores, outcomes, actual, pool,
              f'{status}<br>Deadline {_time(game.get("lock_at"))}<br>Kickoff {_time(game["kickoff"])}')
    cells = []
    for index,(label,value) in enumerate(zip(SEASON_HEADERS[1:],values)):
        attrs = f' class="game-grade-checks" data-grade="{game["grade"]}"' if index == 2 else ''
        cells.append(f'<td role="cell"{attrs}><span class="season-cell-label" aria-hidden="true">{label}</span>'
                     f'<div class="season-cell-value">{value}</div></td>')
    narrative = ('<ol class="season-explanation-steps">' + ''.join(f'<li>{step}</li>' for step in explanation_steps)
                 + '</ol>') if explanation_steps else f'<p>{calculation}</p>'
    return (f'<tr id="season-game-{game_id}" data-season-game-id="{game_id}" class="season-game-row" role="row">'
            f'<th scope="row" role="rowheader">{away} @ {home}</th>' + ''.join(cells) + '</tr>'
            f'<tr class="forecast-reason-row" role="row"><td colspan="7" role="cell">' + _postgame_card(game,comparison) +
            f'<details class="forecast-reason" data-view-key="reason-{game_id}">'
            '<summary>Forecast explanation and availability</summary><div class="forecast-reason-body">'
            f'<div class="forecast-reason-block"><h3>Why this forecast</h3>{narrative}'
            f'<details class="season-calculation" data-view-key="calculation-{game_id}"><summary>Exact saved calculation</summary><p>{calculation}</p>'
            f'<p>Edition: {_text(game.get("source_edition",week["source_edition"]))}.</p>{provenance}</details></div>'
            f'<div class="forecast-reason-block"><h3>Saved forecast availability</h3><p>{note}</p>'
            + (_absences(game) if availability.get('teams') else '') +
            '<p>Non-QB injury news is context, not a fitted injury adjustment.</p></div>'
            + _latest_availability(game,availability_context) + '</div></details></td></tr>')


def _week(week, current, comparisons=None, availability_context=None):
    if week['status'] not in WEEK_STATES: raise ValueError('Unknown week status')
    games = week['games']
    _integer(week['week'])
    if any(game.get('week') != week['week'] for game in games):
        raise ValueError('Season game belongs to another week')
    ids = [game['game_id'] for game in games]
    points = [g['confidence']['points'] for g in games if g.get('confidence') is not None]
    if len(ids) != len(set(ids)) or len(points) != len(set(points)):
        raise ValueError('Duplicate game or confidence allocation in week')
    counts = Counter(game['grade'] for game in games)
    rows = ''.join(_game(game,week,(comparisons or {}).get(game['game_id']),(availability_context or {}).get(game['game_id'])) for game in games)
    allocations = [game['confidence'] for game in games if game.get('confidence') is not None]
    pool_summary = ''
    if allocations:
        earned = sum(c.get('earned_points') or 0 for c in allocations)
        expected = ('Unavailable' if any(c.get('expected_points') is None for c in allocations)
                    else f"{math.fsum(c['expected_points'] for c in allocations):.2f}")
        late = [c for c in allocations if c.get('added_after_lock') is True]
        late_earned = sum(c.get('earned_points') or 0 for c in late)
        unknown = sum(c.get('added_after_lock') is None for c in allocations)
        timing = (f'<strong class="season-late-accounting">Includes {len(late)} late {"entry" if len(late)==1 else "entries"} '
                  f'with {late_earned} earned pool points.</strong> ') if late else ''
        if unknown:
            timing += f'Timing is unknown for {unknown} {"entry" if unknown==1 else "entries"}. '
        qualification = ' Late entries and entries with unknown timing remain in these tracking totals.' if late or unknown else ''
        pool_summary = (f'<p class="season-pool-summary">Confidence pool: {earned} earned so far; '
                        f'{sum(c["points"] for c in allocations)} allocated points. {timing}'
                        f'Expected pool points from the saved chances: {expected}.{qualification}</p>')
    return (f'<details class="forecast-week" id="season-week-{week["week"]}" data-view-key="week-{week["week"]}"{" open" if current else ""}>'
            f'<summary>Week {week["week"]}: {_text(week["status"].replace("_"," "))}</summary>'
            f'<p>Straight-up record: {counts["W"]} W / {counts["L"]} L / {counts["T"]} T; {counts["NO_PICK"]} no pick; {counts["PENDING"]} pending.</p>'
            f'<p>Original forecast saved {_time(week["generated_at"])}; inputs through {_time(week["inputs_as_of"])}.</p>{pool_summary}'
            f'<div class="table-shell" data-view-key="week-table-{week["week"]}"><table class="season-picks-table" role="table"><thead role="rowgroup"><tr role="row">'
            + ''.join(f'<th scope="col" role="columnheader">{header}</th>' for header in SEASON_HEADERS)
            + f'</tr></thead><tbody role="rowgroup">{rows}</tbody></table></div></details>')


def _penalty_shadow(shadow):
    if not shadow:
        return ''
    historical = shadow.get('historical') or {}
    history = ''
    if historical:
        baseline, candidate = (_number(historical[k]) for k in ('baseline_mae','candidate_mae'))
        result = 'met' if historical['status'] == 'PASS' else 'did not meet'
        interval = historical['interval']
        history = (f'<h4>Past-game test: {_integer(historical["games"]):,} games</h4>'
                   '<p>Average error in the predicted lead: '
                   f'existing model <strong>{baseline:.4f}</strong> points; '
                   f'penalty candidate <strong>{candidate:.4f}</strong> points. Lower error is better. '
                   f'The candidate {result} the predeclared improvement screen. '
                   f'It improved {_integer(historical["season_wins"])} of 8 seasons.</p>'
                   f'<p>Estimated improvement range: {_number(interval["lower"]):+.3f} to '
                   f'{_number(interval["upper"]):+.3f} points (95% interval). Positive means less error; '
                   'a range spanning zero does not show a clear gain. These historical seasons have already '
                   'been studied, so future saved predictions are the next test.</p>')
    metrics = shadow.get('metrics') or {}
    paired = _integer(metrics.get('paired_games',0))
    rows = []
    for key, label in (('control','Existing model on the same saved inputs'),('candidate','Penalty candidate')):
        metric = metrics.get(key) or {}
        error = 'Awaiting finals' if metric.get('mae') is None else f'{_number(metric["mae"]):.3f}'
        record = ' / '.join(str(_integer(metric.get(k,0))) for k in ('wins','losses','ties'))
        rows.append(f'<tr><th scope="row">{label}</th><td>{record}</td><td>{error}</td></tr>')
    games = []
    def lead(game, key):
        value = _number(game[key])
        return 'No edge' if value == 0 else f'{_text(game["home"] if value > 0 else game["away"])} by {abs(value):.3g}'
    for game in shadow.get('games',[]):
        grade = game.get('grade') or {}
        labels = [GRADES[grade.get(key,'PENDING')] for key in ('control','candidate')]
        games.append(f'<tr data-penalty-game-id="{_text(game["game_id"])}"><th scope="row">'
                     f'Week {_integer(game["week"])}: {_text(game["away"])} @ {_text(game["home"])}</th>'
                     f'<td>{lead(game,"control_margin")}</td><td>{lead(game,"candidate_margin")}</td>'
                     f'<td>{labels[0]} / {labels[1]}</td><td>{_time(game["issued_at"])}</td></tr>')
    reason = (f'<p><strong>Penalty test update blocked:</strong> {_text(shadow["blocked_reason"])}</p>'
              if shadow.get('blocked_reason') else '')
    excluded = shadow.get('excluded') or []
    exclusions = ('<details data-view-key="penalty-exclusions"><summary>Games excluded from this test</summary><ul>' + ''.join(
        f'<li>{_text(item["game_id"])}: {_text(item["reason"])}</li>' for item in excluded) + '</ul></details>' if excluded else '')
    return ('<details class="model-update-evidence" id="pgo-penalty-test" data-view-key="penalty-test"><summary>Penalty experiment and ongoing results</summary>'
            '<p><strong>Experimental comparison, separate from the main picks.</strong> '
            'This tests whether a team\'s prior penalty yards help predict its next game. Recent games receive more weight; '
            'four games later, an observation has half its original weight. Penalty counts are audited but are not another fitted input.</p>'
            '<p>Weights stay fixed. The scheduled updater checks new finals and prepares future test picks after the weekly '
            'rankings update. Each candidate and comparison pick is saved before the prediction deadline. '
            'Games already locked when the test began, including the NE–SEA opener, do not count toward its future record.</p>'
            + history + reason + f'<h4>Future test: {paired} completed paired games</h4>'
            '<p>The two methods are scored on exactly the same saved games and inputs. A later revision of a main pick '
            'does not replace this saved comparison. Small samples are only progress updates; no automatic model promotion occurs.</p>'
            '<div class="table-shell" data-view-key="penalty-records"><table><thead><tr><th>Test model</th><th>W / L / T</th>'
            '<th>Average lead error (points)</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'
            '<details data-view-key="penalty-picks"><summary>Saved prospective test picks</summary><div class="table-shell" data-view-key="penalty-picks-table"><table><thead>'
            '<tr><th>Matchup</th><th>Existing model lead</th><th>Penalty candidate lead</th>'
            '<th>Grades: existing / candidate</th><th>Saved (Eastern)</th></tr></thead><tbody>'
            + ''.join(games) + '</tbody></table></div></details>' + exclusions +
            '<p>The penalty candidate refits the existing coefficients alongside one new input. Its full prediction change '
            'is not just the new coefficient. This tests scoring margins; it does not supply new score totals, probabilities '
            'or injury adjustments.</p>' + _sources([{'href':shadow.get('source_href','evidence/penalty-model-2026/manifest.json'),
            'label':'Verified weights and historical results'},
            {'href':'https://github.com/walshja9/Postgame_Outlet/blob/main/research/pgo_penalty_candidate/model-card.md',
             'label':'Penalty test methods, findings and review rules'}]) + '</details>')


def _accuracy(summary):
    def number(value, digits=3):
        return 'Awaiting eligible finals' if value is None else f'{_number(value):.{digits}f}'
    def count(metric):
        graded = _integer(metric['n'])
        pending = _integer(metric.get('reasons', {}).get('no_verified_final', 0))
        excluded = _integer(_integer(metric['excluded']) - pending)
        labels = [f'{graded} game{"s" if graded != 1 else ""} graded']
        if pending: labels.append(f'{pending} awaiting final score{"s" if pending != 1 else ""}')
        if excluded: labels.append(f'{excluded} excluded')
        return '; '.join(labels)
    primary = summary['primary']
    probability, confidence = primary['probabilities'], primary['confidence']
    record = primary['record']
    winners = (f'{_integer(record["wins"])} correct; {_integer(record["losses"])} incorrect; '
               f'{_integer(record["ties"])} tied') if record['n'] else 'Awaiting eligible finals'
    cards = [f'<div><dt>Correct winners</dt><dd><strong>{winners}</strong><br>{count(record)}</dd></div>']
    for key, title in (('margin_mae','Average margin error'),('total_mae','Average combined-score error')):
        metric = primary[key]
        value = number(metric['value'],2) + (' points' if metric['value'] is not None else '')
        cards.append(f'<div><dt>{title}</dt><dd><strong>{value}</strong><br>{count(metric)}</dd></div>')
    probability_count = _integer(probability['n'])
    probability_note = ('No eligible pre-lock probabilities have been graded yet.' if probability_count == 0 else
                        'Only 1 eligible game has been graded; too few to judge the win chances.' if probability_count == 1 else
                        f'{probability_count} eligible games have been graded. Small samples cannot establish reliable win chances.')
    earned = confidence['earned_points']
    cards.append(f'<div><dt>Pool points on completed picks</dt><dd><strong>{"Awaiting finals" if earned is None else _integer(earned)} earned</strong>'
                 f'<br>{number(confidence["expected_points"],2)} expected<br>{count(confidence)}'
                 f'<br>{_integer(confidence["late_count"])} late entries; {_integer(confidence["unknown_timing_count"])} with unknown timing</dd></div>')
    comparisons = []
    for model in summary['comparisons']:
        lead,total = model['margin_mae'],model['total_mae']
        comparisons.append(f'<tr><th scope="row">{_text(model["model_name"])}</th>'
                           f'<td>{number(lead["primary"])} / {number(lead["model"])}</td><td>{_integer(lead["n"])}</td>'
                           f'<td>{number(total["primary"])} / {number(total["model"])}</td><td>{_integer(total["n"])}</td></tr>')
    comparison_table = ('<div class="table-shell" data-view-key="accuracy-comparison-table"><table><thead><tr>'
                       '<th>Saved comparison model</th><th>Lead error: weekly / comparison</th><th>Same games</th>'
                       '<th>Total error: weekly / comparison</th><th>Same games</th></tr></thead><tbody>'
                       + ''.join(comparisons) + '</tbody></table></div>') if comparisons else '<p>No separately verified model series supplied for comparison.</p>'
    bins = []
    for row in primary['reliability_bins']:
        chance = 'Unavailable' if row['mean_probability'] is None else f'{_number(row["mean_probability"]):.1%}'
        won = 'Awaiting finals' if row['observed_win_rate'] is None else f'{_number(row["observed_win_rate"]):.1%}'
        bins.append(f'<tr><th scope="row">{_number(row["lower"]):.0%} to {_number(row["upper"]):.0%}</th>'
                    f'<td>{_integer(row["count"])}</td><td>{chance}</td><td>{won}</td></tr>')
    reasons = {'no_verified_final':'No verified final yet','blocked_forecast':'Forecast withheld','unknown_forecast_time':'Forecast time not recorded',
               'late_forecast':'Forecast saved after lock','missing_margin':'No saved lead','missing_total':'No saved total',
               'no_pick':'No selected team','late_confidence':'Probability added after lock','unknown_confidence_time':'Probability timing unknown',
               'incomplete_probabilities':'Full win and tie probabilities not saved','missing_confidence':'Confidence allocation incomplete'}
    exclusions = []
    for key,title in (('margin_mae','Lead error'),('total_mae','Total error'),('probabilities','Probability accuracy'),('confidence','Confidence points')):
        rows = '; '.join(f'{_text(reasons.get(k,k))}: {_integer(v)}' for k,v in primary[key]['reasons'].items()) or 'None'
        exclusions.append(f'<li>{title}: {rows}.</li>')
    return ('<h3 id="season-accuracy">Season accuracy</h3><p>Original saved picks, verified finals. '
            'A correct winner can still come with a poor score estimate. Margin error is how far the predicted winning margin was from the actual margin; '
            'combined-score error is how far the predicted total was from both teams\' final points added together. Lower error is better.</p>'
            '<dl class="season-freshness">' + ''.join(cards) + '</dl>'
            + f'<p><strong>How the win chances are holding up:</strong> {probability_note}</p>'
            '<p class="season-caption">These are early results, not proof of accuracy. Confidence accounting includes marked late entries; '
            'pregame probability accuracy excludes them. Expected points shown here cover the same completed picks as earned points.</p>'
            '<details class="model-update-evidence" data-view-key="accuracy-comparisons"><summary>Compare models on the same games</summary>'
            '<p>Each pair uses exactly the same eligible game IDs for that measure. Errors are in NFL points. '
            'Different model schedules and missing estimates cannot give a model easier games here. '
            'Older score forecasts have no originally saved full probabilities, so they have no pregame probability comparison.</p>'
            + comparison_table + '</details>'
            '<details class="model-update-evidence" data-view-key="accuracy-reliability"><summary>Do the win chances match the results?</summary>'
            '<p>Over many games, picks given about a 60% chance should win about 60% of the time. '
            'The table groups saved chances into fixed ranges and compares them with actual wins. A few results cannot establish reliability; ties count as no selected-team win.</p>'
            '<div class="table-shell" data-view-key="accuracy-reliability-table"><table><thead><tr><th>Saved chance range</th>'
            '<th>Games</th><th>Average saved chance</th><th>Actually won</th></tr></thead><tbody>' + ''.join(bins) + '</tbody></table></div>'
            '<p>Ranges include their lower bound and exclude their upper bound, except the last range includes 100%. '
            '</p><details data-view-key="accuracy-probability-method"><summary>Technical probability scores</summary>'
            f'<p>Brier: {number(probability["brier"])}; Log loss: {number(probability["log_loss"])}. {count(probability)}.</p>'
            '<p>Brier measures squared error across home win, away win and tie, on a 0-to-2 scale. '
            'Log loss penalizes confident misses more strongly. Both improve as they get smaller. '
            'Sample size alone does not establish calibration.</p></details></details>'
            '<details class="model-update-evidence" data-view-key="accuracy-exclusions"><summary>What is not counted?</summary><ul>'
            + ''.join(exclusions) + '</ul><p>These counts refer to the weekly model\'s saved schedule. '
            'The source archives retain every original forecast and its timing.</p></details>')


def _test_table(key, headings, rows):
    return (f'<div class="table-shell" data-view-key="{key}"><table class="model-test-table"><thead><tr>'
            + ''.join(f'<th scope="col">{_text(h)}</th>' for h in headings) + '</tr></thead><tbody>'
            + ''.join('<tr>' + ''.join(f'<td>{cell}</td>' for cell in row) + '</tr>' for row in rows)
            + '</tbody></table></div>')


def _market_benchmark(summary):
    benchmark = summary['benchmark']
    n = _integer(benchmark['n'])
    pending = _integer(benchmark['reasons'].get('pending', 0))
    excluded_count = _integer(_integer(benchmark['excluded']) - pending)
    progress = (f'; {pending} awaiting final score{"s" if pending != 1 else ""}' if pending else '')
    if excluded_count: progress += f'; {excluded_count} excluded'
    cards = []
    for key, label in (('pgo', 'PGO'), ('sportsbook', 'Saved sportsbook forecast')):
        error = benchmark[key + '_margin_mae']
        value = 'Awaiting matched final scores' if error is None else f'{_number(error):.2f} points'
        record = benchmark[key + '_record']
        winners = (f'{_integer(record["wins"])} correct; {_integer(record["losses"])} incorrect; '
                   f'{_integer(record["ties"])} tied; {_integer(record["no_pick"])} no pick') if n else 'Awaiting matched final scores'
        cards.append(f'<div><dt>{label}</dt><dd><strong>{value}</strong> average margin error<br>{winners}</dd></div>')
    difference = benchmark['difference']
    if n and difference is not None:
        gap = _number(difference)
        comparison = (f'{"PGO" if gap < 0 else "The sportsbook forecast"} was {abs(gap):.2f} points closer on average on these games.'
                      if gap else 'Both forecasts had the same average margin error on these games.')
    else:
        comparison = 'Awaiting matched final scores.'
    bands = []
    for row in summary['ats_bands']:
        results = (f'{_integer(row["wins"])} covered; {_integer(row["losses"])} not covered; '
                   f'{_integer(row["pushes"])} pushes; {_integer(row["pending"])} pending; '
                   f'{_integer(row["no_edge"])} no edge')
        bands.append(f'<div><dt>{_text(row["label"])}</dt><dd>{results}</dd></div>')
    excluded = '; '.join(f'{_text(summary.get("reason_labels", {}).get(key, key.replace("_", " ")))}: {_integer(count)}'
                         for key, count in benchmark['reasons'].items()) or 'None'
    return ('<details class="model-update-evidence" id="season-market-benchmark" data-view-key="market-benchmark">'
            '<summary>PGO versus the saved sportsbook forecast</summary>'
            f'<p><strong>{n} matched game{"s" if n != 1 else ""}</strong>{progress}. '
            'Both forecasts are checked against the same final scores. Lower margin error means the predicted winning margin was closer.</p>'
            '<dl class="season-freshness">' + ''.join(cards) + f'</dl><p>{comparison}</p>'
            '<p>This uses the saved DraftKings handicap captured through ESPN before prediction lock. '
            'An even line has no sportsbook favorite; a zero PGO margin has no model winner pick. Tied games and no picks are counted separately. '
            'These results do not establish predictive superiority or profitability.</p>'
            f'<p>Pending games and exclusions: {excluded}.</p>'
            '<details data-view-key="ats-gap-study"><summary>Do larger differences from the sportsbook perform better?</summary>'
            '<p><strong>Descriptive results.</strong> The groups use the absolute difference between the saved PGO margin and sportsbook forecast: '
            'zero, under 1 point, 1 to under 3 points, and 3 or more points. Zero means no ATS edge. '
            'The groups were fixed for this study; earlier outcomes were already known.</p>'
            '<dl class="season-freshness">' + ''.join(bands) + '</dl>'
            f'<p>{_integer(summary["ats"]["unavailable"])} unavailable. Pushes are separate from wins and losses. '
            'There is not enough evidence to adopt a minimum ATS difference. A larger difference is not a verified cover probability. '
            'Original ATS suggestions remain unchanged.</p>'
            '<p><a href="https://github.com/walshja9/Postgame_Outlet/tree/main/research/pgo_ats_gap_20260911">'
            'Fixed study rules and saved evidence</a></p></details></details>')


def _test_value(value, digits=2):
    return 'Awaiting eligible finals' if value is None else f'{_number(value):.{digits}f}'


def _experiments(state):
    totals, weights, depth = (state.get(k) or {} for k in ('totals_shadow','weights_shadow','replacement_depth'))
    usage = state.get('injury_usage') or {}
    if not any((totals, weights, depth, usage)): return ''
    base = 'https://github.com/walshja9/Postgame_Outlet/blob/main/research/'
    panels = []
    if totals:
        names = {'league_prior':'Last season: league average', 'pfpa_prior':'Last season: these teams',
                 'shrink_4':'Update with this season: 4-game starting weight',
                 'shrink_8':'Update with this season: 8-game starting weight'}
        historical, live = totals.get('historical',{}).get('metrics',{}), totals.get('metrics',{})
        rows = [[label, _test_value(historical.get(key,{}).get('mae')),
                 _test_value(live.get(key,{}).get('mae'))] for key,label in names.items()]
        predictions = [[f'{_text(g["away"])} @ {_text(g["home"])}', _time(g['issued_at'])]
                       + [_test_value(g['totals'][key],1) for key in names] for g in totals.get('games',[])]
        panels.append('<details class="model-update-evidence" id="season-totals-test" data-view-key="totals-experiment"><summary>Score totals: can current-season results help?</summary>'
            '<p>Two fixed formulas gradually mix this season\'s scoring with last season\'s. A 4-game starting weight means '
            'last season counts like four games; the 8-game version changes more slowly. Only verified results from earlier game days can enter.</p>'
            f'<p>Monitor: {_text(totals["status"])}. {_text(totals.get("blocked_reason") or "")}</p>'
            '<p><strong>Both updating formulas passed the historical further-study screen.</strong> The 4-game version reduced '
            'average total error from 11.04 to 10.74 points across the same 2,127 games. This is a reason to keep testing, '
            'not proof of live improvement. The current main score estimates remain unchanged.</p>'
            + _test_table('totals-results', ['Scoring rule','Historical total error (points)','New-game total error (points)'], rows)
            + f'<p>New comparison: {_integer(len(totals.get("games",[])))} saved matchups; '
            f'{_integer(live.get("paired_games",0))} verified finals on identical games for all four rules. '
            'Formal review requires at least 150 paired games across 12 weeks. No automatic model change.</p>'
            '<details data-view-key="totals-issued"><summary>Original test estimates for upcoming and completed games</summary>'
            + _test_table('totals-picks', ['Matchup','Saved (Eastern)','League prior','Team prior','4-game weight','8-game weight'], predictions)
            + '</details><p>Lower average absolute error is better. Historical seasons have been reused, and original source timing still needs review. '
            f'<a href="{base}pgo_totals_candidate_20260910/README.md">Methods, season checks and saved evidence</a>.</p></details>')
    if weights:
        from pgo_forecast_lab import _spread
        arms = {'postseason':'Current input blocks', 'without_qb_passing':'Without QB passing block',
                'without_team_passing':'Without team passing block'}
        curves = {'scalar':'same neutral midpoint','intercept':'learned midpoint'}
        historical, live = weights.get('historical',{}), weights.get('metrics',{})
        rows = [[label, _test_value(historical.get('margin_arms',{}).get(key,{}).get('mae')),
                 _test_value(live.get('margin_arms',{}).get(key,{}).get('mae'))] for key,label in arms.items()]
        probability_rows = []
        for arm,label in arms.items():
            for curve,description in curves.items():
                key = f'{arm}_{curve}'; past = historical.get('probability_curves',{}).get(key,{})
                future = live.get('probability_curves',{}).get(key,{})
                probability_rows.append([f'{label}; {description}', _test_value(past.get('log_loss'),4),
                                         _test_value(past.get('brier'),4), _test_value(future.get('log_loss'),4)])
        issued = []
        for game in weights.get('games',[]):
            items = []
            for arm,label in arms.items():
                margin = _number(game['margins'][arm])
                lead = _spread(dict(home=game['home'],away=game['away'],margin=margin))
                chances = []
                for curve,description in curves.items():
                    value = game['probabilities'][f'{arm}_{curve}']
                    chance = (f'{_text(value["selected_team"])} {_number(value["selected_probability"]):.1%}'
                              if value.get('selected_team') else 'No selected team')
                    chances.append(f'{description}: {chance}')
                items.append(f'<li>{label}: {lead}. Win chances &mdash; {"; ".join(chances)}.</li>')
            issued.append(f'<details data-view-key="weights-game-{_text(game["game_id"])}"><summary>{_text(game["away"])} @ {_text(game["home"])}</summary>'
                          f'<p>Saved {_time(game["issued_at"])}. Lead estimates are NFL points; percentages are straight-up win chances.</p><ul>'
                          + ''.join(items) + '</ul></details>')
        panels.append('<details class="model-update-evidence" id="season-weights-test" data-view-key="weights-experiment"><summary>Inputs and win chances: test overlap without guessing new weights</summary>'
            '<p>Recent results, team passing and quarterback passing can describe the same games. We tested removing one passing block at a time '
            'and refitted each fixed variant using earlier seasons only. We also tested two ways to convert each lead into a win chance.</p>'
            f'<p>Monitor: {_text(weights["status"])}. {_text(weights.get("blocked_reason") or "")}</p>'
            '<p><strong>No alternative cleared the improvement screen.</strong> Removing either block made average lead error slightly worse. '
            'None of the probability alternatives met the required improvement and uncertainty checks. The main model stays unchanged.</p>'
            + _test_table('weights-results',['Input choice','Historical lead error (points)','New-game lead error (points)'],rows)
            + '<p>All lead tests use the same 2,127 historical games. Probability tests use the same 1,615 later games, '
            'after allowing earlier seasons to train the probability method. Lower error, log loss and Brier are better.</p>'
            + _test_table('probability-results',['Probability method','Historical log loss','Historical Brier (0–2)','New-game log loss'],probability_rows)
            + '<p>A learned midpoint lets the probability method move its 50/50 boundary; it can change the selected team even when the lead estimate stays fixed. '
            'That is why these test picks are tracked separately. Fixed confidence points are not reassigned.</p>'
            f'<p>New comparison: {_integer(len(weights.get("games",[])))} saved matchups; {_integer(live.get("paired_games",0))} paired finals. '
            'Historical results are diagnostic and source timing still needs review.</p>'
            '<details data-view-key="weights-issued"><summary>Original test picks and probabilities</summary>' + ''.join(issued) + '</details>'
            f'<p><a href="{base}pgo_weights_candidate_20260910/README.md">Every variant, review rules and saved evidence</a>.</p></details>')
    if depth:
        inventory = depth.get('teams', [])
        if depth.get('inventory_version') in (1, 2) and inventory and all(
                team.get('inventory_version') == depth['inventory_version'] and isinstance(team.get('defenders'), list) for team in inventory):
            count = sum(len(team['defenders']) for team in inventory)
            inventory_note = (f'{count} named defender record{"s" if count != 1 else ""} saved. '
                              'Later snap reports can show who played; they do not prove who replaced whom or how many points an injury cost.')
            if depth.get('status') != 'DESCRIPTIVE / NOT IN MODEL':
                inventory_note = 'The latest defender update could not be verified. The earlier named inventory remains preserved.'
            if depth['inventory_version'] == 1:
                inventory_note += ' This older inventory omitted roster-listed inactive players; its original counts are preserved.'
            else:
                inventory_note += ' Roster-listed inactive players are retained as dated context; that label does not establish absence for an upcoming game.'
        else:
            inventory_note = ('This saved edition lacks the complete named defender inventory. '
                              'New captures will retain it; older captures are not filled in afterward.')
        teams = []
        for team in depth.get('teams',[]):
            rows = [[_text(role['position'])] + [str(_integer(role[key])) for key in
                     ('listed_first','confirmed_unavailable_first','remaining_experienced_backups_not_confirmed_out',
                      'remaining_unknown_history_backups_not_confirmed_out','uncertain_backups')] for role in team.get('roles',[])]
            unavailable = []
            for player in team.get('unavailable_players',[]):
                prior = ('Prior usage unknown' if player.get('prior_role_share') is None else
                         f'2025 observed playing-time share: {_number(player["prior_role_share"]):.1%}')
                status = 'Confirmed unavailable' if player.get('confirmed_unavailable') else 'Uncertain availability'
                unavailable.append(f'<li>{_text(player["name"])} ({_text(player["position"])}): {status}; '
                                   f'roster {_text(player["roster_status"])}. {prior}.</li>')
            code = _text(team['team'])
            inactive_names = [p['name'] for p in team.get('defenders', []) if p.get('roster_status') == 'INA'] if depth.get('inventory_version') == team.get('inventory_version') == 2 else []
            inactive_note = ('<p>Roster-listed inactive defenders: ' + ', '.join(_text(name) for name in inactive_names)
                             + '. This may describe an earlier game; use the current game\'s official report to check availability.</p>') if inactive_names else ''
            unresolved = sorted(set(team.get('unresolved_official_names',[]) + [r['name'] for r in team.get('unresolved_roster',[])]))
            teams.append(f'<details data-view-key="replacement-team-{code}"><summary>{code} &middot; defensive depth observations</summary>'
                f'<p>Provider depth list: {_time(team.get("depth_snapshot_at"))}. Official report: {_text(team["report_status"])}; '
                f'final inactives: {_text(team["final_inactives_status"])}. Report checked: {_time(team.get("availability_checked_at"))}.</p>'
                + _test_table(f'replacement-roles-{code}', ['Provider position','Listed first','First-listed unavailable',
                    'Backups with prior usage; not confirmed out','Backups with unknown history; not confirmed out','Uncertain backups'], rows)
                + f'<p>Unresolved depth names: {_integer(team["depth_identity_conflicts"])}. '
                f'Active defenders missing from depth list: {_integer(team["unlisted_active_defenders"])}. '
                f'Unavailable defenders with unknown prior role: {_integer(team["unavailable_unknown_prior_role"])}.</p>'
                + inactive_note
                + ('<p>Names awaiting identity resolution: ' + ', '.join(_text(name) for name in unresolved) + '.</p>' if unresolved else '')
                + ('<ul>' + ''.join(unavailable) + '</ul>' if unavailable else '<p>No unavailable players resolved in these saved sources; this does not establish full health.</p>')
                + '</details>')
        panels.append('<details class="model-update-evidence" id="season-defender-info" data-view-key="replacement-experiment"><summary>Injuries and defensive backups: what we can verify</summary>'
            f'<p>Capture: {_text(depth["status"])}. {_text(depth.get("blocked_reason") or "")} '
            f'Saved {_time(depth.get("generated_at"))}; newest source {_time(depth.get("source_as_of"))}.</p>'
            '<p><strong>No numerical injury adjustment yet.</strong> We now save dated player identities, provider depth positions, '
            'known absences and prior defensive usage for future evaluation. The historical audit found no dated historical depth sources '
            'or source-capture clocks in the admitted inventory, so it cannot support a fitted injury or replacement-quality effect.</p>'
            '<p>Prior playing time describes experience, not talent. Unknown history stays unknown, including rookies. Active roster status '
            'does not prove health; a backup not confirmed out is not confirmed available. Provider position labels are kept as supplied. '
            'Multiple defensive packages can list more than eleven players first. These latest observations do not revise locked forecasts.</p>'
            f'<p>{_integer(len(depth.get("teams",[])))} team summaries; {_integer(len(depth.get("games",[])))} unlocked matchups captured. '
            'Official report coverage is stated separately for each team.</p>'
            + f'<p>{inventory_note} <a href="{base}pgo_defender_inventory_20260911/README.md">Named defender usage checks</a>.</p>' + ''.join(teams)
            + '<details data-view-key="replacement-sources"><summary>Captured roster and depth sources</summary>'
            + _sources(depth.get('sources',[])) + '</details>'
            f'<p><a href="{base}pgo_replacement_depth_20260910/README.md">Admission audit, missing information and capture history</a>.</p>'
            f'<p><a href="{base}pgo_injury_usage_20260911/README.md">Injury and replacement-usage study</a>.</p></details>')
    validation = (
        '<details class="model-update-evidence" id="season-injury-validation" data-view-key="injury-validation">'
        '<summary>Do injury adjustments improve PGO yet?</summary>'
        '<p><strong>Not established. Injury news is shown, but non-QB point adjustments have not qualified for the picks.</strong> '
        'The earlier test covered 2,127 games. Its average margin error was 10.099 points with the old availability terms '
        'and 10.097 without them: essentially unchanged. That test also included quarterback absences, so it cannot settle the non-QB question.</p>'
        '<p>The September 12 source audit found that the saved 2025 injury records lack update times. '
        'We cannot establish which version of those reports was known before each prediction. '
        'The fresh playing-time file covers both opening games, but none of the 14 unavailable defenders saved before SF–LAR '
        'has a matching row. A player missing from that file is unknown, not automatically zero plays.</p>'
        '<p>We are checking original pregame defender lists against later playing-time reports. '
        'This tells us whether the data can support a fair test; it does not yet tell us how many points an injury costs. '
        'Offensive player coverage and a separate test of forecast accuracy are still required.</p>')
    if usage:
        if usage.get('forecast_adjustment') is not None or usage.get('predictive_status') != 'UNAVAILABLE':
            raise ValueError('Defender usage is descriptive, not a forecast adjustment')
        if usage.get('status') == 'BLOCKED':
            validation += ('<p><strong>Playing-time check needs review.</strong> '
                           + _text(usage.get('blocked_reason') or 'The latest check could not be verified.')
                           + ' Earlier saved evidence is retained.</p>')
        else:
            metrics = usage.get('metrics') or {}
            validation += (
                f'<p>Automatic check saved {_time(usage.get("checked_at"))}. '
                f'Eligible completed games: {_integer(metrics.get("games", 0))}. '
                f'Games awaiting finals: {_integer(usage.get("pending_games", 0))}. '
                f'Completed games without an eligible saved list: {_integer(len(usage.get("excluded_games", [])))}.</p>')
            validation += (
                f'<p>Matched playing-time rows: {_integer(metrics.get("joined", 0))} of '
                f'{_integer(metrics.get("cohort_rows", 0))}; '
                f'{_integer(metrics.get("observed_positive", 0))} recorded playing time, '
                f'{_integer(metrics.get("observed_zero", 0))} explicitly recorded zero, '
                f'{_integer(metrics.get("missing_target", 0))} have no matching row. '
                'Repeated checks do not add extra games or players to the sample.</p>'
                if metrics.get('cohort_rows') else '<p>No completed player records are eligible yet. '
                'Playing-time coverage will appear when eligible games finish and their snap reports arrive.</p>')
        validation += _sources([dict(href='evidence/season-2026/' + usage[key]['path'], label=label)
                                for key, label in (('report', 'Last saved playing-time report'),
                                                   ('source', 'Captured playing-time source receipt')) if usage.get(key)])
    else:
        validation += '<p>The automatic playing-time check has no saved result yet.</p>'
    panels.append(validation + f'<p><a href="{base}pgo_nonqb_validation_20260912/README.md">'
                  'Validation findings, data gaps and next test</a>.</p></details>')
    panels.append('<details class="model-update-evidence" data-view-key="score-range-study"><summary>How much could the score vary?</summary>'
        '<p><strong>Reliable outcome ranges are not available yet.</strong> The displayed score is an average estimate, '
        'not a narrow promise about the final score. We tested a fixed range method on historical games, using only earlier '
        'seasons to set each later season\'s range. Those reused records lack the timestamps needed to establish pregame data availability.</p>'
        '<p>Future saved ranges need to be checked against actual results before we can describe them as reliable. '
        'Differences between model versions are not the same as a likely range of game outcomes.</p>'
        f'<p><a href="{base}pgo_score_ranges_20260911/README.md">Score-range study and validation requirements</a>.</p></details>')
    return ('<h3 id="season-model-tests">Model tests</h3><p>These fixed comparisons are separate from the main picks. '
            'Test forecasts are saved before lock and graded when verified finals arrive. Defender checks compare saved player lists '
            'with later playing time. Games without eligible pregame evidence are excluded. '
            'No experiment automatically replaces the main model.</p>' + ''.join(panels))


def render_season(state, *, accuracy=None, mccabe=None, market=None):
    """Render validated saved state using the existing shared PGO styles once per page."""
    if state['schema_version'] != 1 or state['status'] not in ('READY','BLOCKED'):
        raise ValueError('Unknown season view state')
    season, current = _integer(state['season']), _integer(state['current_week'])
    if accuracy is None:
        from pgo_season_accuracy import summarize
        accuracy = summarize(state)
    ats_view = ''
    comparisons = {}
    if state.get('ats'):
        from pgo_ats_view import render
        ats_view = render(state['ats'])
        comparisons = {g['game_id']:g for key in ('games','unavailable') for g in state['ats'].get(key,[])}
    weeks = state['weeks']
    if len({w['week'] for w in weeks}) != len(weeks): raise ValueError('Duplicate season week')
    games = [game for week in weeks for game in week['games']]
    if len({game['game_id'] for game in games}) != len(games) or any(game.get('season') != season for game in games):
        raise ValueError('Season game identity is duplicated or belongs to another season')
    records = []
    for row in state.get('model_records', []):
        counts = ''.join(f'<td>{_integer(row[key])}</td>' for key in ('wins','losses','ties','no_pick','pending'))
        records.append(f'<tr><th scope="row">{_text(row["name"])}<br><small>{_text(row["edition"])}</small></th>{counts}</tr>')
    block = f'<p><strong>Update blocked:</strong> {_text(state["blocked_reason"])}</p>' if state.get('blocked_reason') else ''
    failed_updates = [f'<a href="#{anchor}">{label}</a>' for key, anchor, label in (
        ('penalty_shadow', 'pgo-penalty-test', 'Penalty test'),
        ('totals_shadow', 'season-totals-test', 'Score-total test'),
        ('weights_shadow', 'season-weights-test', 'Model-input tests'),
        ('replacement_depth', 'season-defender-info', 'Defender information'),
        ('injury_usage', 'season-injury-validation', 'Injury validation checks'),
        ('ats', 'season-ats', 'Sportsbook comparisons')) if (state.get(key) or {}).get('status') == 'BLOCKED']
    update_note = ('<p class="season-caption">Separate updates needing review: ' + ', '.join(failed_updates)
                   + '. Earlier saved information is retained.</p>') if failed_updates else ''
    main_status = 'Latest refresh completed' if state['status'] == 'READY' else 'Update needs review'
    current_weeks = ''.join(_week(w,True,comparisons,state.get('availability_context')) for w in weeks if w['week'] == current)
    archives = ''.join(_week(w,False,comparisons,state.get('availability_context')) for w in sorted(weeks,key=lambda w:w['week'],reverse=True) if w['week'] != current)
    links = [('season-game-day','Game day')]
    if current_weeks: links.append((f'season-week-{current}',f'Week {current} picks'))
    if state.get('rankings'): links.append(('season-rankings','Rankings'))
    links.append(('season-records','Winner records'))
    more = [('season-accuracy','Accuracy')]
    if state.get('ats'): more.append(('season-ats','Spreads & ATS'))
    if state.get('penalty_shadow'): more.append(('pgo-penalty-test','Penalty test'))
    if any(state.get(k) for k in ('totals_shadow','weights_shadow','replacement_depth','injury_usage')):
        more.append(('season-model-tests','Model tests'))
    navigation = '<nav class="season-nav" aria-label="PGO sections">' + ''.join(
        f'<a href="#{target}" data-view-key="nav-{target}">{label}</a>' for target,label in links)
    navigation += ('<details class="season-nav-more" data-view-key="nav-more"><summary>More</summary><div>'
                   + ''.join(f'<a href="#{target}" data-view-key="nav-{target}">{label}</a>' for target,label in more)
                   + '</div></details></nav>')
    return (f'<div class="pgo-model-updates" id="pgo-season" data-season-checked-at="{_text(state["checked_at"])}"><h2>PGO Power Rankings &mdash; Experimental</h2>'
            f'<p><strong>{season} &middot; Week {current} &middot; EXPERIMENTAL / HOLD.</strong> '
            'Accuracy is still being tested. The record below tracks saved forecasts.</p>'
            + navigation + '<details class="model-update-evidence" data-view-key="numbers-guide"><summary>How the numbers connect</summary>'
            '<p>Team ratings measure model strength from recent results and team/quarterback history. '
            'The home rating minus the away rating is the projected home-team point advantage at a neutral site with equal rest. '
            'The saved venue and rest adjustments then give the game lead. Each individual rating is centered model strength, '
            'not a standalone score prediction. '
            'A separate scoring estimate sets combined points; the lead splits those points into two score averages. '
            'That scoring estimate uses the saved 2025 regular-season and playoff scoring and points-allowed averages; '
            'it does not yet update with 2026 results.</p>'
            '<p>Win probability is a percentage from the saved model probability method, not a rating or a confidence-point percentage. '
            'Fixed confidence points weight the picks within one weekly pool. Points times win probability gives expected '
            'pool points, not NFL scoreboard points. None of these numbers guarantees a result.</p>'
            '<p>Rounded score estimates can look equal even when one team has a small edge. '
            'About 25 points each is not a prediction of a tied game. Open Model averages for decimal estimates.</p>'
            f'<p>{_text(state.get("freshness", ""))}</p>'
            '<p>Rankings update after a complete week and verified statistics; '
            'an expected-quarterback change can also revise unlocked picks. Forecast availability refreshes before prediction lock. Final inactive checks continue separately around kickoff; a check does not mean every player is healthy. '
            'Overdue means more than 30 minutes for availability or 45 minutes for results and automation.</p>'
            '<p><strong>The main W/L/T records grade straight-up winners. Spread comparisons have separate records below.</strong> '
            'Any victory by the selected team earns a W, regardless of the winning margin. '
            'Lead error separately measures how close the predicted margin was. The predicted lead is a model estimate, not a sportsbook line. '
            'Grades use saved picks and verified final scores. Missing results remain pending. '
            'Injury news is shown as context; current non-QB injuries and backup quality are not separately rated.</p></details>'
            f'<p class="season-caption"><strong>Main picks and grades:</strong> {main_status}. '
            'Non-QB injuries and backup quality are context, not fitted adjustments.</p>' + block + update_note
            + _freshness(state) + _inactive_watch(state) + _game_day(state) + _rankings(state.get('rankings'),mccabe) +
            '<h3 id="season-records">Winner records (straight-up)</h3>'
            '<p>W: the selected team won. L: the selected team lost. T: the game ended in a tie. '
            'Sportsbook spread records are tracked separately.</p>'
            '<div class="table-shell" data-view-key="model-records-table"><table><thead><tr><th>Saved model series</th>'
            '<th>W</th><th>L</th><th>T</th><th>No pick</th><th>Pending</th></tr></thead>'
            f'<tbody>{"".join(records)}</tbody></table></div>'
            '<p>Each record covers its own saved schedule. Weekly editions cover published weeks; '
            'the preseason baselines cover all 272 regular-season games, so their pending counts can be larger.</p>'
            + _accuracy(accuracy) + (_market_benchmark(market) if market is not None else '') +
            f'<h3>Week {current} picks and grades</h3>'
            '<p>Winner grades count who won. Each game also shows how its saved picks compared with the PGO projection '
            'and sportsbook line. A correct winner can fall below the projected margin or fail to cover the spread.</p>'
            '<p><strong>Fixed confidence points:</strong> the weekly allocation is saved once. '
            'Before a game locks, an expected-QB update may change its win chance without reallocating its confidence points. '
            'Expected pool points = fixed points times win chance; these are not NFL scoreboard points. '
            'After-lock confidence entries are marked separately and are not pregame probability evidence; '
            'the original score forecast keeps its own saved timing.</p>'
            + (current_weeks or '<p>No saved slate is available for this week.</p>') +
            ('<details class="model-update-evidence" data-view-key="week-archives"><summary>Previous weekly grades and forecasts</summary>' + archives + '</details>' if archives else '') +
            _penalty_shadow(state.get('penalty_shadow')) +
            ats_view +
            _experiments(state) +
            '<details class="model-update-evidence" data-view-key="season-sources"><summary>Sources and limitations</summary>'
            + _sources(state.get('sources', [])) + '<ul>' + ''.join(f'<li>{_text(item)}</li>' for item in state.get('limitations', [])) + '</ul></details></div>')
