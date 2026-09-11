"""Present the selected verified edition and preserve earlier boards for comparison."""
from datetime import datetime
import html
import math
import re
from zoneinfo import ZoneInfo

import generate_site

START = '<!-- PGO CURRENT BOARD START -->'
END = '<!-- PGO CURRENT BOARD END -->'
ARCHIVE_OPEN = ('<!-- PGO JULY ARCHIVE OPEN --><details class="pgo-july-archive">'
                '<summary>July 21, 2026 comparison archive</summary>')
ARCHIVE_CLOSE = '</details><!-- PGO JULY ARCHIVE CLOSE -->'


def strip_current_board(page):
    """Recover the exact legacy markup before its existing strict validators run."""
    counts = [page.count(marker) for marker in (START, END, ARCHIVE_OPEN, ARCHIVE_CLOSE)]
    if counts == [0, 0, 0, 0]:
        return page
    if counts != [1, 1, 1, 1] or not (
            page.index(START) < page.index(END) < page.index(ARCHIVE_OPEN) < page.index(ARCHIVE_CLOSE)):
        raise ValueError('Invalid current-board/archive presentation markers')
    page = re.sub(re.escape(START) + r'.*?' + re.escape(END), '', page, count=1, flags=re.S)
    return page.replace(ARCHIVE_OPEN, '', 1).replace(ARCHIVE_CLOSE, '', 1)


def _time(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Current board source timestamps require a timezone')
    return (f'<time datetime="{html.escape(value, quote=True)}">'
            f'{parsed.astimezone(ZoneInfo("America/New_York")):%B %d, %Y at %I:%M %p %Z}</time>')


def team_identity(code, name=None):
    """Render the shared team marker/chip without changing model identity."""
    match = next(((team, colors) for team, colors in generate_site.TEAM.items()
                  if colors[0] == code), None)
    full_name, colors = match or (name or code, (code, "#445", "#889"))
    label = name or full_name
    return (
        f'<span class="pgo-team-marker" style="--team-primary:{colors[1]};'
        f'--team-secondary:{colors[2]}" aria-hidden="true"></span>'
        f'<span class="pgo-team-chip" aria-hidden="true">{html.escape(code)}</span>'
        f'<span class="pgo-team-name">{html.escape(label)}</span>'
    )


def rating_bar(value, scale=14.0):
    """Render the model output on a signed scale while retaining 3-decimal text."""
    fraction = max(-1, min(1, value / scale))
    side = "left:50%" if fraction >= 0 else "right:50%"
    kind = "pos" if fraction > 0 else "neg" if fraction < 0 else "zero"
    clipping = "; bar clipped at scale maximum" if abs(value) > scale else ""
    return (
        f'<span class="pgo-rating-bar" role="img" '
        f'aria-label="PGO rating {value:+.3f} on a -{scale:g} to +{scale:g} scale{clipping}">'
        '<span class="pgo-rating-track" aria-hidden="true"><span class="pgo-rating-mid"></span>'
        f'<span class="pgo-rating-fill {kind}" style="{side};width:{abs(fraction) * 50:.1f}%"></span>'
        '</span></span>'
    )


def add_current_board(page, snapshot=None, mccabe_rows=None):
    # Lab imports comparison; defer these imports until rendering is requested.
    import pgo_comparison as comparison
    import pgo_forecast_corrected as corrected
    from pgo_availability_view import render_current_scenario
    from pgo_model_updates import EDITION as selected_edition, render_current_updates
    page = strip_current_board(page)
    if snapshot is None:
        import pgo_forecast_lab as lab
        weekly = lab.pgo_forecast_weekly.load_weekly(lab.WEEKLY_DIR)
        snapshot, _directory = lab._load_corrected(None, weekly, lab.WEEKLY_DIR)
    if snapshot['edition'] != corrected.EDITION:
        raise ValueError('Current board requires the corrected September 8 edition')
    if mccabe_rows is None:
        mccabe_rows = comparison.load_mccabe_rows(comparison.MCCABE_PATH)
    human = {row['abbr']: row for row in mccabe_rows}
    teams = sorted(snapshot['teams'], key=lambda row: row['rank'])
    if (len(teams) != 32 or len(human) != 32 or {row['team'] for row in teams} != set(human)
            or [row['rank'] for row in teams] != list(range(1, 33))
            or any(not math.isfinite(row['rating']) for row in teams)
            or teams != sorted(teams, key=lambda row: (-row['rating'], row['team']))):
        raise ValueError('Current board requires 32 verified ranked team identities')
    rows = []
    ne_rank = next(team['rank'] for team in teams if team['team'] == 'NE')
    for team in teams:
        code, rank = team['team'], team['rank']
        name = human[code]['team']
        mccabe_rank = human[code]['rank']
        rows.append(
            f'<tr data-current-pgo-team="{html.escape(code, quote=True)}">'
            f'<td class="pgo-rank pgo-essential">{rank}</td>'
            f'<th scope="row" class="pgo-team pgo-essential"><a href="https://walshja9.github.io/Postgame_Outlet/forecast-lab.html#corrected-rating-{code}" '
            f'target="_blank" rel="noopener noreferrer">{team_identity(code, name)}</a></th>'
            f'<td class="pgo-rating-value pgo-essential" data-value="{team["rating"]}">{team["rating"]:+.3f}</td>'
            f'<td class="pgo-rating-scale pgo-detail">{rating_bar(team["rating"])}</td>'
            f'<td class="pgo-detail">{html.escape(team["qb_name"])}</td>'
            f'<td class="pgo-detail">{mccabe_rank}</td><td class="pgo-detail">{rank - mccabe_rank:+d}</td></tr>')
    updates = render_current_updates(include_original=False)
    selected = 'id="pgo-season"' in updates or f'data-edition="{selected_edition}"' in updates
    if updates:
        from pgo_forecast_lab import FORECAST_DISPLAY_SCRIPT
        updates += FORECAST_DISPLAY_SCRIPT
    current = (
        f'<div class="pgo-current-board" data-edition="{corrected.EDITION}">'
        '<div class="model-status" data-model-status="HOLD">Experimental — still being tested</div>'
        '<h2>PGO Corrected — September 8, 2026</h2>'
        '<p>Higher ratings mean the model expects a stronger team. These numbers are not betting lines. '
        '“Corrected” means we repaired the calculation; greater accuracy has not been proved.</p>'
        '<p><strong>Injuries beyond the quarterback are not included.</strong> '
        'These ratings assume the listed quarterback plays.</p>'
        f'<p>Roster information saved through {_time(snapshot["inputs_as_of"])}. '
        'Game and player performance comes from the 2025 regular season and earlier. '
        'Select a team to see why it ranks here. Team explanations open in a new tab.</p>'
        f'<p><strong>New England is #{ne_rank} in this snapshot.</strong> '
        'Past results and passing performance help put New England here. '
        'The model includes past team defense results, but does not separately rate current '
        'edge-rusher or linebacker depth, or the quality of their backups. '
        'This is not a complete assessment of today\'s roster. '
        '<a href="https://walshja9.github.io/Postgame_Outlet/forecast-lab.html#corrected-rating-NE" '
        'target="_blank" rel="noopener noreferrer">Read New England’s explanation</a>.</p>'
        '<details><summary>How to read this board — dates and technical details</summary>'
        '<p>Research status: EXPERIMENTAL / HOLD. Zero is the average of these 32 teams. '
        'A +5 rating does not mean a team should be favored by five points.</p>'
        f'<p>Snapshot generated {_time(snapshot["generated_at"])}. '
        f'McCabe source: {_time(comparison.mccabe_source_timestamp(comparison.MCCABE_PATH))}. '
        'Performance history ends with the 2025 regular season.</p>'
        '<p>“vs McCabe” compares rank positions: +3 means PGO ranks the team three spots lower. '
        'It is PGO rank minus McCabe rank, not a difference in points. '
        '<a href="https://walshja9.github.io/Postgame_Outlet/forecast-lab.html#corrected-ratings" '
        'target="_blank" rel="noopener noreferrer">Forecast Lab: explanations, source coverage, and weekly drafts</a>. '
        '</p></details>'
        '<label class="pgo-column-toggle" for="current-pgo-columns">'
        '<input id="current-pgo-columns" type="checkbox"> Show QB and McCabe comparison</label>'
        '<div class="table-shell"><table class="current-pgo-table">'
        '<caption class="visually-hidden">All 32 teams: corrected PGO model output and current McCabe rank</caption>'
        '<thead><tr><th scope="col" class="pgo-essential">Rank</th>'
        '<th scope="col" class="pgo-essential">Team</th>'
        '<th scope="col" class="pgo-essential">PGO rating</th>'
        '<th scope="col" class="pgo-detail"><span class="pgo-scale-label"><span aria-hidden="true">-14</span><span>Rating scale</span><span aria-hidden="true">+14</span></span></th>'
        '<th scope="col" class="pgo-detail">Expected QB</th>'
        '<th scope="col" class="pgo-detail">McCabe #</th><th scope="col" class="pgo-detail">vs McCabe</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>{render_current_scenario()}</div>')
    if selected:
        current = (updates + '<details class="pgo-previous-models" id="previous-models">'
                   '<summary>Compare previous models</summary>' + current + '</details>')
    else:
        current += updates
    current = START + current + END
    panel = comparison.extract_comparison_panel(page)
    opening = panel.index('>') + 1
    closing = panel.rindex('</section>')
    updated = panel[:opening] + current + ARCHIVE_OPEN + panel[opening:closing] + ARCHIVE_CLOSE + panel[closing:]
    return page.replace(panel, updated, 1)
