"""Additive presentation of separately verified model updates; never issues forecasts."""
import html
import hashlib
import math
import json
from pathlib import Path

import pgo_current_board

EDITION = 'pgo-postseason-week1-2026-09-09'
ROOT = Path(__file__).resolve().parent
DEFAULT_DIR = ROOT / 'docs/evidence/forecast-lab-2026/september-09-postseason'
DEFENSE_TEST_DIR = ROOT / 'research/pgo_defensive_depth_candidate/run-20260909-attempt01'
DEFENSE_TEST_MANIFEST_SHA256 = 'd23b20fb253ad13d00bd71807c89ecad5368868f06bb146418ac2eb47d422f92'
CONFIDENCE_MANIFEST_SHA256 = '4fc0b0972bfc29b72d783fe2d3b12fd0f4b290ae4b400d8e18f7b2e24cc55437'
FULL_CONFIDENCE_MANIFEST_SHA256 = 'ae8f685dd636052d428e0e2cc9b5e0d853bcaa6dfcb876daa0bd5d7a451c89b2'

STYLE = """<style>
.pgo-model-updates{margin-top:28px;padding-top:24px;border-top:1px solid var(--border)}
:is(.pgo-model-updates,.pgo-current-board,.pgo-july-archive,.lab-wrap) .table-shell{overflow-x:auto;container-type:inline-size}
.pgo-model-updates table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
.pgo-model-updates th,.pgo-model-updates td{padding:9px;border-bottom:1px solid var(--border);text-align:right;vertical-align:top;white-space:nowrap}
.pgo-model-updates td.game-grade-checks{min-width:12rem;max-width:16rem;white-space:normal;text-align:left}
@container(min-width:680px){:is(.pgo-model-updates,.pgo-current-board,.pgo-july-archive,.lab-wrap) table :is(th,td){padding:8px 6px;white-space:normal;overflow-wrap:anywhere}:is(.pgo-model-updates,.pgo-current-board,.pgo-july-archive,.lab-wrap) table th{overflow-wrap:normal}.pgo-availability table{min-width:0}}
.pgo-model-updates tbody th{text-align:left;letter-spacing:normal;text-transform:none;background:var(--panel);color:var(--ink)}
.pgo-model-updates summary{cursor:pointer;font-weight:700}
.pgo-model-updates .forecast-week{margin:12px 0;padding:12px;border:1px solid var(--border);border-radius:10px}
.pgo-model-updates .forecast-reason-row>td{text-align:left;padding:0 9px 10px;white-space:normal}
.pgo-model-updates .forecast-reason{width:min(960px,calc(100cqw - 18px));max-width:100%;font-size:13px;font-weight:400;line-height:1.5}
.pgo-model-updates .forecast-reason>summary{padding:7px 0}
.pgo-model-updates .forecast-reason-body{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:12px;padding:8px 0}
.pgo-model-updates .forecast-reason-block{min-width:0;padding:14px;border:1px solid var(--border);border-radius:8px;background:var(--panel);white-space:normal;overflow-wrap:anywhere}
.pgo-model-updates .forecast-reason-block h3{margin:0 0 8px;font-size:14px;color:var(--accent)}
.pgo-model-updates .forecast-reason-block p{margin:0 0 10px;white-space:normal}
.pgo-model-updates .forecast-reason-block p:last-child{margin-bottom:0}
.pgo-model-updates .forecast-reason-calculation{margin-top:12px}
.pgo-model-updates .model-update-evidence{margin:16px 0}
.pgo-model-updates .lab-detail,.pgo-previous-models{margin:12px 0;padding:12px;border:1px solid var(--border);border-radius:10px}
.pgo-previous-models>summary{cursor:pointer;font-weight:800}
.pgo-model-updates .rating-explanation table{table-layout:fixed}
.pgo-model-updates .rating-explanation th{white-space:normal;overflow-wrap:anywhere}
.pgo-model-updates .rating-explanation td{font-size:12px}
.pgo-model-updates .model-update-evidence li{margin:8px 0;overflow-wrap:anywhere}
.pgo-model-updates .model-update-columns{display:none;align-items:center;gap:8px;margin:12px 0}
.pgo-confidence{margin:24px 0;padding:18px;border:1px solid var(--border);border-top:4px solid var(--orange);border-radius:10px;background:var(--panel)}
.pgo-confidence .confidence-summary{display:flex;flex-wrap:wrap;gap:18px;margin:16px 0}
.pgo-confidence .confidence-summary strong{display:block;font-size:26px;color:var(--accent)}
.pgo-confidence .confidence-summary span{font-size:13px}.pgo-confidence .confidence-table th{white-space:normal;min-width:80px}
.pgo-confidence .confidence-table a{font-weight:700}.pgo-confidence .confidence-note{font-size:13px;line-height:1.5}
@media(max-width:700px){.pgo-model-updates .pgo-team-name{display:none}.pgo-model-updates .model-update-columns{display:flex}.postseason-team-table .model-update-extra{display:none}.model-update-columns:has(input:checked)+.table-shell .model-update-extra{display:table-cell}}
</style>"""


def _text(value):
    return html.escape(str(value), quote=True)


def _block(title, content):
    return f'<div class="forecast-reason-block"><h3>{_text(title)}</h3>{content}</div>'


def _reason(game, snapshot):
    # Every game comes directly from this verified package, not the weekly ledger.
    from pgo_challenger import _rest_difference
    from pgo_forecast_lab import _spread
    teams = {row['team']: row for row in snapshot['teams']}
    home, away = game['home'], game['away']
    margin, total = game['margin'], game['total']
    for actual, expected in ((game['home_points'], (total + margin) / 2),
                             (game['away_points'], (total - margin) / 2)):
        if not math.isclose(actual, expected, rel_tol=0, abs_tol=1e-9):
            raise ValueError('Candidate saved scores do not reconcile')
    fit = snapshot['fit']
    pp = fit['preprocessor']
    def coefficient(name):
        index = pp['feature_names'].index(name)
        return fit['coefficients'][index + 1] / pp['scales'][index]
    gap = teams[home]['rating'] - teams[away]['rating']
    venue = 0.0 if game['location'] == 'Neutral' else coefficient('home_field')
    rest_input = _rest_difference(game['home_rest'], game['away_rest'])
    rest = None if rest_input is None else rest_input * coefficient('rest_difference')
    edge = f'<p>Saved candidate: {_spread(game)}.</p>'
    if rest is not None and math.isclose(gap + venue + rest, margin, rel_tol=0, abs_tol=1e-9):
        venue_text = ('The neutral site adds no home advantage.' if game['location'] == 'Neutral'
                      else f'Playing at home adds {venue:.1f} points for {_text(home)}.')
        rest_text = ('Both teams have the same rest, so there is no rest adjustment.'
                     if game['home_rest'] == game['away_rest'] else
                     f'The rest adjustment adds {rest:+.2f} points to the home-team lead; '
                     'the difference in days is capped at seven.')
        edge = (f'<p>Before the venue adjustment: {_spread({**game, "margin": gap})}. '
                f'{venue_text} {rest_text} That leaves {_spread(game)}.</p>')
    rates = snapshot['scoring_rates']
    values = [rates[team][kind] for team in (away, home) for kind in ('pf', 'pa')]
    if not math.isclose(math.fsum(values) / 2, total, rel_tol=0, abs_tol=1e-9):
        raise ValueError('Candidate scoring history does not reconcile')
    history = snapshot['history']
    body = _block('How the edge is built', edge)
    body += _block('What changed',
        '<p>This candidate includes regular season and playoffs in its historical team and '
        'quarterback inputs. The September 8 model used regular-season history. '
        'More history does not automatically make the prediction more accurate.</p>'
        f'<p>Expected quarterbacks: {_text(away)}: {_text(teams[away]["qb_name"])}; '
        f'{_text(home)}: {_text(teams[home]["qb_name"])}. Their history is already in the ratings.</p>')
    body += _block('Combined points',
        f'<p>Using the {history["scoring_season"]} regular season and playoffs: '
        f'{_text(away)} averaged {values[0]:.2f} scored and {values[1]:.2f} allowed '
        f'over {rates[away]["games"]} games; {_text(home)} averaged {values[2]:.2f} scored '
        f'and {values[3]:.2f} allowed over {rates[home]["games"]} games. '
        f'Add these four averages and divide by two: {total:.2f} combined points.</p>'
        '<p>Playoff teams have more games in these averages. This remains a simple scoring-history estimate.</p>')
    body += _block('What is still missing',
        '<p>Current non-QB player quality and the quality of defensive backups are not fitted '
        'adjustments in this candidate. The defensive-depth evidence below is descriptive. '
        'It does not add or subtract points from this forecast.</p>')
    calculation = (
        f'<p>Home score = (combined points + home-team lead) / 2: '
        f'({total:.2f} + ({margin:+.2f})) / 2 = {game["home_points"]:.2f}. '
        f'Away score = (combined points - home-team lead) / 2 = {game["away_points"]:.2f}. '
        'Displayed figures are rounded; saved values keep full precision.</p>'
        f'<p>September 8 comparison: {_spread({**game, "margin": game["corrected_margin"]})}; '
        f'{game["corrected_total"]:.2f} combined points.</p>'
        f'<p>Saved edition: {_text(snapshot["edition"])}. '
        'EXPERIMENTAL / HOLD. This explains the calculation, not certainty about the result.</p>')
    return ('<details class="forecast-reason"><summary>Why this forecast</summary>'
            f'<div class="forecast-reason-body">{body}</div>'
            '<details class="forecast-reason-block forecast-reason-calculation">'
            f'<summary>Full calculation and saved version</summary>{calculation}</details></details>')


def _candidate(snapshot, weekly=None, results=(), provenance=(), *, depth_available=False, confidence=None, confidence_archive=None):
    from pgo_forecast_lab import _forecast_weeks, _forecast_reason, snapshot_interim_metrics, _snapshot_metric_cards, _https_url, _spread, _corrected_section
    if snapshot['edition'] != EDITION or snapshot['method']['status'] != 'EXPERIMENTAL / HOLD':
        raise ValueError('Model update requires the separate experimental postseason edition')
    teams = sorted(snapshot['teams'], key=lambda row: row['rank'])
    expected = {row[0] for row in pgo_current_board.generate_site.TEAM.values()}
    if (len(teams) != 32 or {row['team'] for row in teams} != expected
            or [row['rank'] for row in teams] != list(range(1, 33))
            or any(not math.isfinite(row['rating']) for row in teams)
            or teams != sorted(teams, key=lambda row: (-row['rating'], row['team']))):
        raise ValueError('Candidate requires all 32 verified ranked teams')
    validation = snapshot['validation']
    if validation['status'] not in ('PASS', 'FAIL'):
        raise ValueError('Candidate historical screen status is unavailable')
    outcome = ('passed the historical screen' if validation['status'] == 'PASS'
               else 'did not pass the historical screen')
    ne = next(team for team in teams if team['team'] == 'NE')
    opener = next((game for game in snapshot['games'] if {game['home'], game['away']} == {'NE', 'SEA'}), None)
    injury_link = ('<a href="#latest-inactive-notes">Final inactive announcements and source times</a>'
                   if depth_available else 'Latest final-inactive context is unavailable in this view')
    comparison = (f'<p><strong>New England moves from #{ne["baseline_rank"]} to #{ne["rank"]} in this candidate. '
                  f'This candidate {outcome} and remains EXPERIMENTAL / HOLD.</strong> '
                  + (f'Its Seattle matchup favors {_spread(opener)}. '
                     f'<a href="#postseason-why-{_text(opener["game_id"])}">Why this forecast</a>.' if opener else '') + '</p>')
    rows = []
    for team in teams:
        code = team['team']
        rows.append(f'<tr data-postseason-team="{_text(code)}">'
            f'<td class="pgo-rank">{team["rank"]}</td>'
            f'<th scope="row" class="pgo-team"><a href="#postseason-rating-{_text(code)}">{pgo_current_board.team_identity(code)}</a></th>'
            f'<td class="pgo-rating-value" data-value="{team["rating"]}">{team["rating"]:+.3f}</td>'
            f'<td>{team["rank"] - team["baseline_rank"]:+d}</td>'
            f'<td class="model-update-extra pgo-rating-scale">{pgo_current_board.rating_bar(team["rating"])}</td>'
            f'<td class="model-update-extra">{team["baseline_rating"]:+.3f}</td>'
            f'<td class="model-update-extra">{_text(team["qb_name"])}</td></tr>')
    games = snapshot['games'] if weekly is None else weekly['games']
    source_games = {game['game_id']: game for game in snapshot['games']}
    fields = ('game_id', 'season', 'week', 'game_type', 'home', 'away', 'kickoff',
              'location', 'home_rest', 'away_rest', 'margin', 'total', 'home_points', 'away_points')
    reasons = {}
    for game in games:
        if weekly is None:
            matches = True
        else:
            if game.get('source_edition') != EDITION:
                raise ValueError('Candidate ledger contains another model edition')
            source = source_games.get(game['game_id'])
            matches = (source is not None and snapshot.get('_manifest_sha256')
                       and game['source_manifest_sha256'] == snapshot['_manifest_sha256']
                       and game['source_generated_at'] == snapshot['generated_at']
                       and all(game.get(key) == source.get(key) for key in fields))
        reason = _reason(game, snapshot) if matches else _forecast_reason(game)
        reasons[game['game_id']] = reason.replace('<details class="forecast-reason"',
            f'<details id="postseason-why-{_text(game["game_id"])}" class="forecast-reason"', 1)
    metrics = snapshot_interim_metrics({**snapshot, 'games': games}, results)
    results_sources = ''.join(f'<li><a href="{_text(_https_url(item["source_url"]))}">'
                             f'Shared final-result source</a>; {_text(item["captured_at"])}</li>' for item in provenance)
    history = snapshot['history']
    limits = ''.join(f'<li>{_text(item)}</li>' for item in validation['limitations'])
    return (
        f'<div id="postseason-model-update" data-edition="{EDITION}">'
        '<div class="model-status" data-model-status="HOLD">EXPERIMENTAL / HOLD</div>'
        '<h2>PGO Power Rankings &mdash; Experimental</h2>'
        '<p><strong>September 9, 2026 edition.</strong> Postseason history is included in the '
        'team and quarterback inputs. This is the main public PGO view; earlier models, saved '
        'forecasts and grades remain available below. Displaying this version does not establish greater accuracy.</p>'
        '<p><strong>Injury reports are shown as context, not numerical adjustments to these ratings '
        'or saved forecasts.</strong> The listed quarterback is assumed to play. '
        f'{injury_link} &middot; '
        '<a href="#previous-models">Compare previous models</a>.'
        + (' <a href="#pgo-confidence-picks">PGO confidence picks and expected pool points</a>.' if confidence is not None else '') + '</p>'
        f'<p><strong>This candidate {outcome}.</strong> Average margin error was '
        f'{validation["candidate_mae"]:.3f} points, compared with {validation["baseline_mae"]:.3f} '
        f'for the baseline on the same {validation["games"]} games. Lower is better. '
        'These reused historical seasons do not establish future accuracy.</p>'
        f'{comparison}'
        f'<p>Inputs saved through {pgo_current_board._time(snapshot["inputs_as_of"])}. '
        f'Candidate created {pgo_current_board._time(snapshot["generated_at"])}.</p>'
        '<h3>All 32 PGO ratings</h3><p>Higher ratings mean stronger model output; zero is '
        'the 32-team average. Rank change is candidate rank minus September 8 rank, so a positive '
        'number means a lower position. Ratings are model units, not betting lines.</p>'
        '<label class="model-update-columns"><input type="checkbox"> Show rating scale, earlier rating and QB</label>'
        '<div class="table-shell"><table class="postseason-team-table"><thead><tr>'
        '<th>Rank</th><th>Team</th><th>PGO rating</th><th>Rank change</th>'
        '<th class="model-update-extra">Rating scale (-14 to +14)</th>'
        '<th class="model-update-extra">September 8 rating</th>'
        '<th class="model-update-extra">Expected QB</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
        '<details class="model-update-evidence" id="postseason-explanations"><summary>Why teams rank here</summary>'
        f'{_corrected_section(snapshot, latest_inactive_notes=depth_available)}</details>'
        + (render_confidence_picks(confidence, results) if confidence is not None else '') +
        ('<details class="model-update-evidence"><summary>Earlier 15-game confidence allocation</summary>'
         + render_confidence_picks(confidence_archive, results, archive=True) + '</details>'
         if confidence_archive is not None else '') +
        '<h3>September 9 saved matchups</h3><p>Scores are rounded averages. Open Model averages '
        'for decimals. About 25 points each means both estimates round to 25, not a predicted '
        'tie. The favored team uses the unrounded margin. These September 9 records have their own grades; earlier versions remain available, '
        'and no saved forecast is rewritten.</p>'
        f'{_forecast_weeks(games, results, weekly=weekly is not None, reasons=reasons, series="postseason", incumbent_label="September 8 corrected")}'
        f'<h3>September 9 forecast record and grades</h3><p>{len(results)} of {len(games)} saved September 9 forecasts '
        'have final results. Interim grades include misses as well as hits; they are not scientific promotion.</p>'
        f'{_snapshot_metric_cards(metrics, "postseason candidate", incumbent_label="September 8 corrected margin")}'
        '<details class="model-update-evidence"><summary>Testing, history and saved source</summary>'
        f'<p>History includes {_text(", ".join(history["game_types"]))}: '
        f'{history["regular_games"]} regular-season and {history["postseason_games"]} playoff games. '
        f'History through {pgo_current_board._time(history["through"])}.</p>'
        f'<p>Seasons with lower error: {validation["season_wins"]}. Paired error-reduction interval: '
        f'{validation["interval"]["lower"]:+.3f} to {validation["interval"]["upper"]:+.3f}. '
        'This is a historical comparison, not a range for a game result.</p>'
        f'<ul>{limits}</ul><ul>{results_sources}</ul><p><a href="evidence/forecast-lab-2026/september-09-postseason/snapshot.json">'
        'Saved candidate inputs and outputs</a> &middot; '
        '<a href="evidence/forecast-lab-2026/september-09-postseason/manifest.json">Package verification</a>'
        '</p></details></div>')


def _depth_evidence(depth, coverage=None):
    from pgo_forecast_lab import _https_url
    if depth['status'] != 'DESCRIPTIVE / NOT IN MODEL' or depth['forecast_adjustment'] is not None:
        raise ValueError('Defensive depth evidence must not imply a fitted forecast adjustment')
    teams = sorted(depth['teams'], key=lambda row: row['team'])
    expected = {row[0] for row in pgo_current_board.generate_site.TEAM.values()}
    if len(teams) != 32 or {team['team'] for team in teams} != expected:
        raise ValueError('Defensive depth requires all 32 team identities')
    def cell(value):
        return 'Unavailable' if value is None else _text(value)
    rows, details = [], []
    columns = ('active_defenders', 'listed_starters', 'listed_backups',
               'backups_with_prior_defensive_snaps', 'backups_without_prior_defensive_snaps',
               'unlisted_defenders')
    for team in teams:
        code = team['team']
        rows.append(f'<tr data-depth-team="{_text(code)}"><th scope="row">'
            f'<a href="#depth-players-{_text(code)}">{pgo_current_board.team_identity(code)}</a></th>'
            + ''.join(f'<td>{cell(team[key])}</td>' for key in columns) + '</tr>')
        players = []
        report = (coverage or {}).get(code, {})
        report_source = ''
        if report.get('captured_at'):
            report_source = (f'<p>Earlier forecast-input report notes captured {pgo_current_board._time(report["captured_at"])}. '
                             f'<a href="{_text(_https_url(report["source_url"]))}">Earlier official report source</a>. These are archived input notes; the later final inactive announcements below take precedence.</p>')
        for player in team['players']:
            observations = [row for row in report.get('observations', [])
                            if row.get('gsis_id') and row['gsis_id'] == player['gsis_id']]
            injury = ''
            if len(observations) == 1:
                row = observations[0]
                note = ('Game designation: ' + row['game_status'] if row.get('game_status') else
                        'Practice report: ' + row['practice_status'] if row.get('practice_status') else
                        'No game designation listed')
                injury = f'<br><small>{_text(note)}</small>'

            roles = ', '.join(f'{row["position"]} #{row["rank"]}' for row in player['depth_rows'])
            players.append('<tr>'
                f'<th scope="row">{_text(player["name"])}<br><small>{_text(player["gsis_id"])}</small></th>'
                f'<td>{_text(player["position"])} / {_text(player["roster_status"])}<br>'
                f'{_text(roles or "Not assigned a verified depth role")}<br>{_text(player["depth_status"])}{injury}</td>'
                + ''.join(f'<td>{cell(player.get(key))}</td>' for key in
                          ('defensive_snaps', 'def_sacks', 'def_qb_hits', 'def_tackles_for_loss',
                           'def_pass_defended', 'def_interceptions'))
                + f'<td>{_text(player["history_status"])}<br>{cell(player["observed_games"])} observed games<br>'
                  f'{_text(", ".join(player["previous_teams"]) or "No prior team recorded")}</td></tr>')
        clock = ('Depth snapshot time unavailable' if team['depth_snapshot_at'] is None else
                 pgo_current_board._time(team['depth_snapshot_at']))
        details.append(f'<details class="model-update-evidence" id="depth-players-{_text(code)}">'
            f'<summary>{_text(code)}: player roles and prior production</summary>'
            f'<p>Data coverage: {_text(team["coverage_status"])}. {clock}. '
            'ACT, RES, DEV and EXE are source roster-status labels; reserve players are not assumed available.</p>'
            f'{report_source}'
            '<div class="table-shell"><table><thead><tr><th>Player</th><th>Position / roster / depth</th>'
            '<th>Defensive snaps</th><th>Sacks</th><th>QB hits</th><th>Tackles for loss</th>'
            '<th>Passes defended</th><th>Interceptions</th><th>History coverage</th></tr></thead>'
            f'<tbody>{"".join(players)}</tbody></table></div></details>')
    sources = []
    for source in depth['sources']:
        label = source.get('file') or 'Source'
        url = source.get('url')
        link = f'<a href="{_text(_https_url(url))}">{_text(label)}</a>' if url else _text(label)
        captured = (pgo_current_board._time(source['captured_at']) if source.get('captured_at')
                    else 'Capture time unavailable')
        sources.append(f'<li>{link}; {captured}; SHA-256 <code>{_text(source.get("sha256", "Unavailable"))}</code></li>')
    limitations = ''.join(f'<li>{_text(value)}</li>' for value in depth['limitations'])
    return (
        '<div id="defensive-depth-update"><h2>Defensive depth: what the sources show</h2>'
        '<p><strong>DESCRIPTIVE / NOT IN MODEL.</strong> This evidence does not change any rating or forecast. '
        'It shows current listed roles and past defensive playing time and production; it is not a talent ranking.</p>'
        '<p>A rookie or player without matched history is unknown, not automatically a poor replacement. '
        'Position labels are preserved from the source: not every linebacker is an edge rusher. '
        'Past production does not isolate player quality or prove that the same role continues. '
        'Listed first means rank one in a source position or subpackage slot; a team can have '
        'more than eleven such listings. It is not an inferred starting lineup.</p>'
        f'<p>Current inputs through {pgo_current_board._time(depth["inputs_as_of"])}; '
        f'package created {pgo_current_board._time(depth["generated_at"])}. '
        f'Historical window: {_text(depth["historical_window"])}.</p>'
        '<p>ACT is an active-roster status, not a promise that a player will play. These counts include '
        'players with injury designations. No injury note does not establish that a player is healthy.</p>'
        '<p id="latest-inactive-notes"><strong>Final inactives: Patriots rechecked at 7:15 PM Eastern; Seattle checked at 6:52 PM:</strong> '
        'Seattle confirmed Nick Emmanwori and Tory Horton inactive; New England also listed Erick Hunter inactive. '
        'These later announcements do not change the captured roster counts or saved forecasts.</p>'
        '<details class="model-update-evidence"><summary>Tonight\'s official inactive lists</summary>'
        '<p><a href="https://www.patriots.com/news/inactives-analysis-patriots-elevate-rb-lan-larison-from-practice-squad-with-treveyon-henderson-inactive-for-season-opener-vs-seahawks">New England</a>: '
        'Karon Prunty, TreVeyon Henderson (ankle), Erick Hunter, Walter Rouse, Ben Brown (knee) and Efton Chism III; '
        'Behren Morton is designated the emergency quarterback.</p>'
        '<p><a href="https://www.seahawks.com/news/nick-emmanwori-tory-horton-inactive-for-seahawks-opener-vs-patriots">Seattle</a>: '
        'Nick Emmanwori, Tory Horton, Ty Okada, Nick Kallerup, Beau Stephens and Mike Morris; '
        'Jalen Milroe is designated the emergency third quarterback.</p></details>'
        '<p><strong>Seattle roster update, September 9:</strong> '
        '<a href="https://www.seahawks.com/news/seahawks-make-roster-moves-ahead-of-season-opener-vs-patriots">'
        'The club announced</a> AJ Finley joining the 53-player roster, Rodney Thomas II and Velus Jones Jr. '
        'being elevated, and Bryce Cabeldue being waived. Those moves are missing from this captured '
        'provider roster. The table and saved forecasts retain their dated inputs.</p>'
        '<p>Select a team for player-level evidence. A backup with past snaps has recorded experience, '
        'not a verified quality grade. Missing depth roles and missing history stay explicit.</p>'
        '<div class="table-shell"><table><thead><tr><th>Team</th><th>ACT roster defenders</th>'
        '<th>Listed first</th><th>Listed backups</th><th>Backups with past snaps</th>'
        '<th>Backups without past snaps</th><th>Unlisted defenders</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>{"".join(details)}'
        '<details class="model-update-evidence"><summary>Depth sources and limitations</summary>'
        f'<ul>{limitations}</ul><ul>{"".join(sources)}</ul></details></div>')


def render_defense_test(summary):
    """Present an independently verified diagnostic; do not blend its predictions."""
    from pgo_forecast_lab import _https_url
    if summary['status'] not in ('PASS', 'FAIL'):
        raise ValueError('Unknown defensive test screen')
    outcome = 'passed the historical screen' if summary['status'] == 'PASS' else 'did not pass the historical screen'
    ne = summary.get('ne')
    movement = (f' On the same fresh inputs, New England moved from #{ne["baseline_rank"]} '
                f'in the control to #{ne["rank"]} in this diagnostic. Rank movement is not evidence '
                'that a model is more accurate.' if ne else '')
    return (
        '<div id="defense-production-test"><h2>Defensive-production test</h2>'
        '<p><strong>EXPERIMENTAL / HOLD.</strong> This separate test added prior defensive '
        'activity, experienced-contributor breadth, and history coverage to the September 8 '
        'construction. It does not use current depth-chart order as a fitted feature or grade backup talent.</p>'
        f'<p><strong>It {outcome}.</strong> Average margin error: '
        f'{summary["candidate_mae"]:.3f} points versus {summary["baseline_mae"]:.3f} for the baseline '
        f'on the same {summary["games"]} games; lower is better. '
        f'It improved {summary["season_wins"]} of 8 seasons.{movement}</p>'
        '<p>These results are not added to the postseason forecasts. Previously inspected '
        'historical seasons and uneven source coverage limit what this test can establish.</p>'
        '<details class="model-update-evidence"><summary>Defensive test result and source</summary>'
        f'<p>Paired error-reduction interval: {summary["interval"]["lower"]:+.3f} to '
        f'{summary["interval"]["upper"]:+.3f} points. This compares historical error; '
        'it is not an uncertainty range for a game forecast.</p>'
        f'<ul>{"".join(f"<li>{_text(item)}</li>" for item in summary["limitations"])}</ul>'
        f'<p><a href="{_text(_https_url(summary["report_url"]))}">Full model-update report</a>. '
        f'Verified research manifest: <code>{_text(summary["manifest_sha256"])}</code>.</p></details></div>')


def _load_defense_test():
    if not DEFENSE_TEST_DIR.exists():
        return None
    from research.pgo_input_audit.audit_model import _verified_manifest
    _verified_manifest(DEFENSE_TEST_DIR, DEFENSE_TEST_MANIFEST_SHA256)
    metrics = json.loads((DEFENSE_TEST_DIR / 'metrics.json').read_bytes())
    receipt = json.loads((DEFENSE_TEST_DIR / 'run-receipt.json').read_bytes())
    if receipt['status'] != 'EXPERIMENTAL / HOLD':
        raise ValueError('Defensive research must retain HOLD')
    candidate, baseline = (metrics['metrics'][key]['overall'] for key in ('candidate', 'corrected'))
    screen = metrics['further_study_screen']
    return dict(status=screen['status'], candidate_mae=candidate['mae'], baseline_mae=baseline['mae'],
                games=candidate['count'], season_wins=screen['season_wins'],
                interval=metrics['paired_bootstrap']['vs_corrected'],
                ne=next(row for row in json.loads((DEFENSE_TEST_DIR / 'current-ratings.json').read_bytes()) if row['team'] == 'NE'),
                limitations=['Historical source publication vintage remains under review.',
                             'Missing identities and statistic exposure are excluded and reported, not treated as zero ability.',
                             'The fixed diagnostic screen does not remove EXPERIMENTAL / HOLD.'],
                manifest_sha256=DEFENSE_TEST_MANIFEST_SHA256,
                report_url='https://github.com/walshja9/Postgame_Outlet/blob/main/docs/model-update-2026-09-09.md')


def render_updates(snapshot=None, depth=None, *, weekly=None, results=(), provenance=(), defense_test=None, confidence=None, confidence_archive=None):
    if snapshot is None and depth is None and defense_test is None:
        return ''
    return ('<div class="pgo-model-updates" id="model-updates">' + STYLE
            + (_candidate(snapshot, weekly, results, provenance, depth_available=depth is not None, confidence=confidence, confidence_archive=confidence_archive) if snapshot is not None else '')
            + (render_defense_test(defense_test) if defense_test is not None else '')
            + (_depth_evidence(depth, snapshot.get('coverage') if snapshot else None) if depth is not None else '') + '</div>')


def render_current_updates():
    snapshot, weekly, results, provenance = None, None, [], []
    if DEFAULT_DIR.exists() or DEFAULT_DIR.is_symlink():
        from pgo_forecast_postseason import load_snapshot
        import pgo_forecast_lab as lab
        snapshot = load_snapshot(DEFAULT_DIR)
        snapshot = {**snapshot, '_manifest_sha256': hashlib.sha256((DEFAULT_DIR / 'manifest.json').read_bytes()).hexdigest()}
        candidate_ledger = DEFAULT_DIR.parent / 'weekly-postseason'
        if candidate_ledger.exists() or candidate_ledger.is_symlink():
            weekly = lab.pgo_forecast_weekly.load_weekly(candidate_ledger)
            original = lab.pgo_forecast_weekly.load_weekly(lab.WEEKLY_DIR)
            union = {game['game_id']: game for game in original['games']}
            identity = lab.pgo_forecast_weekly._IDENTITY_KEYS
            for game in weekly['games']:
                prior = union.get(game['game_id'])
                if prior and any(game.get(key) != prior.get(key) for key in identity):
                    raise ValueError('Candidate result identity differs from the original ledger')
                union[game['game_id']] = game
            accepted, provenance = lab.load_results(lab.WEEKLY_DIR / 'results', {'games': list(union.values())})
            candidate_ids = {game['game_id'] for game in weekly['games']}
            results = [result for result in accepted if result['game_id'] in candidate_ids]
    depth = None
    depth_dir = DEFAULT_DIR.parents[1] / 'defensive-depth-2026/september-09'
    if depth_dir.exists() or depth_dir.is_symlink():
        from research.pgo_defensive_depth_candidate.validation import load_verified
        depth = load_verified(depth_dir, optional=True)
    confidence = confidence_archive = None
    confidence_dir = DEFAULT_DIR.parents[1] / 'confidence-pool-2026/week1-remaining'
    if snapshot is not None and (confidence_dir.exists() or confidence_dir.is_symlink()):
        from pgo_confidence_full_slate import load_remaining_verified
        confidence = load_remaining_verified(confidence_dir, CONFIDENCE_MANIFEST_SHA256, snapshot)
    full_dir = confidence_dir.parent / 'week1-full'
    if snapshot is not None and (full_dir.exists() or full_dir.is_symlink()):
        from pgo_confidence_full_slate import load_verified
        confidence_archive = confidence
        confidence = load_verified(full_dir, FULL_CONFIDENCE_MANIFEST_SHA256, snapshot)
    earlier = render_updates(snapshot, depth, weekly=weekly, results=results, provenance=provenance,
                             defense_test=_load_defense_test(), confidence=confidence, confidence_archive=confidence_archive)
    from pgo_season import load_current
    season = load_current(DEFAULT_DIR.parents[1] / 'season-2026')
    if season is None:
        return earlier
    from pgo_season_view import render_season
    from pgo_season_accuracy import load_models, summarize
    accuracy = summarize(dict(season, accuracy_models=load_models()))
    return (STYLE + render_season(season, accuracy=accuracy)
            + '<p><a href="#latest-inactive-notes">Opening-night final inactive lists saved September 9</a>.</p>'
            + '<details class="model-update-evidence" id="opening-week-editions">'
            '<summary>Original Week 1 editions and confidence allocations</summary>'
            + earlier.replace(STYLE, '', 1) + '</details>')


def render_confidence_picks(pool, results=(), *, archive=False):
    """Explain a verified, frozen model-derived pool allocation without refitting."""
    from pgo_confidence_picks import grade
    if pool['status'] != 'EXPERIMENTAL / HOLD':
        raise ValueError('Confidence probabilities must retain experimental status')
    grades = grade(pool, results)
    full = pool.get('kind') == 'full-slate-after-lock'
    accuracy = grade({**pool, 'games': [g for g in pool['games'] if not g['added_after_lock']]}, results) if full else grades
    section_id = 'pgo-confidence-previous' if archive else 'pgo-confidence-picks'
    row_attribute = 'data-confidence-archive-game-id' if archive else 'data-confidence-game-id'
    evidence_directory = 'week1-full' if full else 'week1-remaining'
    slate_label = f'full slate &middot; {len(pool["games"])} games' if full else f'{len(pool["games"])} remaining games'
    earned_label = 'Full-slate points earned' if full else 'Points earned so far'
    games = sorted(pool['games'], key=lambda game: -game['confidence_points'])
    rows = []
    for game in games:
        earned = grades['games'].get(game['game_id'])
        rows.append(
            f'<tr {row_attribute}="{_text(game["game_id"])}">'
            f'<th scope="row"><a href="#postseason-why-{_text(game["game_id"])}">'
            f'{_text(game["away"])} @ {_text(game["home"])}</a>'
            + ('<br><small>Added after lock</small>' if game.get('added_after_lock') else '') + '</th>'
            f'<td><strong>{_text(game["selected_team"])}</strong></td>'
            f'<td>{game["win_probability"] * 100:.1f}%</td>'
            f'<td>{game["confidence_points"]}</td>'
            f'<td>{game["expected_points"]:.2f}</td>'
            f'<td>{earned["earned_points"] if earned is not None else "&mdash;"}</td></tr>')
    excluded = '; '.join(f'{_text(row["away"])} @ {_text(row["home"])}' for row in pool['excluded'])
    metrics = ''
    if accuracy['finalized_games']:
        metrics = '<p>Probability grades (lower is better): ' + '; '.join(
            f'{_text(name)} log loss {value["log_loss"]:.4f}, Brier {value["brier"]:.4f}'
            for name, value in accuracy['metrics'].items()) + '. Interim results, not proof of accuracy.</p>'
    if full:
        metrics += (f'<p>{accuracy["finalized_games"]} eligible final results in probability accuracy grades. '
                    'Rows added after lock are excluded from these grades. The full-slate earned-point '
                    'total above includes them for tracking only.</p>')
    return (
        f'<div class="pgo-confidence" id="{section_id}">'
        '<h3>PGO confidence picks</h3><p><strong>EXPERIMENTAL / HOLD.</strong> '
        f'Week 1 &middot; {slate_label}. These picks and win chances come from '
        'the September 9 postseason model.</p>'
        '<p>We give the most confidence points to PGO\'s strongest win chances. '
        '<strong>Expected pool points = confidence points &times; the picked team\'s win chance.</strong> '
        'These are confidence-pool points, not NFL scoreboard points.</p>'
        '<div class="confidence-summary">'
        f'<div><span>Expected pool points</span><strong>{pool["expected_points_total"]:.2f}</strong>'
        f'<span>{sum(g["confidence_points"] for g in games)} points available across this slate</span></div>'
        f'<div><span>{earned_label}</span><strong>{grades["earned_points"]}</strong>'
        f'<span>{grades["finalized_games"]} of {len(games)} final results recorded</span></div></div>'
        + ('<p class="confidence-note"><strong>NE @ SEA is included; its confidence calculation was added after lock.</strong> '
           'The original game forecast was saved before lock. This full-slate allocation is not a pregame pool submission; '
           'the earlier 15-game allocation remains available below.</p>' if full else '')
        + (f'<p class="confidence-note"><strong>{excluded} was already locked when this layer was created.</strong> '
           'It receives no new confidence allocation. Its original prediction remains in the saved matchups. '
           'This is a remaining-games slate, not a full 16-game pool entry.</p>' if excluded else '') +
        '<div class="table-shell" role="region" aria-label="PGO model confidence picks" tabindex="0">'
        '<table class="confidence-table"><thead><tr><th scope="col">Matchup</th><th scope="col">PGO pick</th>'
        '<th scope="col">Model win chance</th><th scope="col">Confidence points</th>'
        '<th scope="col">Expected pool points</th><th scope="col">Earned points</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
        '<p class="confidence-note">Win chances are experimental estimates, not guarantees. '
        'Non-QB injuries are not numerical adjustments in these saved forecasts. '
        'The listed quarterback is assumed to play. A loss or tie earns zero pool points.</p>'
        '<details class="model-update-evidence"><summary>How PGO calculates and grades these picks</summary>'
        '<p>The model first predicts the home team\'s scoring margin. A probability curve fitted '
        'to 2018&ndash;2025 historical out-of-fold forecasts converts that margin into home-win, away-win '
        'and tie probabilities. The team with the larger win probability is the pick. '
        'This curve preserves the model\'s favorite and its ordering by margin size.</p>'
        f'<p>Confidence points run from 1 through {len(games)}, used once each. '
        'Multiplying each allocation by its win chance gives its expected contribution; we add those '
        'contributions for the total. The calculation uses full precision before display rounding. '
        'Maximizing expected points is different from maximizing the chance of finishing first.</p>'
        f'<p>Saved {pgo_current_board._time(pool["generated_at"])}. Allocations stay fixed as games lock. '
        'Official final results supply earned points and probability grades; pending games are not counted as losses.</p>'
        f'{metrics}<p>The historical test showed only a small improvement and reused previously examined seasons. '
        'Historical source timing and calibration transfer remain limitations. Live probability accuracy '
        'has not been established.</p><p>'
        f'<a href="evidence/confidence-pool-2026/{evidence_directory}/picks.json">Saved model picks and exact calculation</a> &middot; '
        f'<a href="evidence/confidence-pool-2026/{evidence_directory}/manifest.json">Verification record</a> &middot; '
        '<a href="https://github.com/walshja9/Postgame_Outlet/blob/main/docs/confidence-pool-study.md">Historical probability test</a> &middot; '
        '<a href="confidence-pool.html">Try your own probability assumptions</a></p></details></div>')
