"""Pure rendering of saved PGO lines and separate against-the-spread records."""


def render(ats):
    from pgo_season_view import _text, _time, _number, _integer, _test_table, _sources

    ats = ats or {}

    def signed(value):
        value = _number(value)
        if value == 0:
            return '0'
        return f'{value:+.3g}' if abs(value) < .001 else f'{value:+.3f}'.rstrip('0').rstrip('.')

    def line(team, handicap):
        return 'Unavailable' if handicap is None else _text(team) + ' ' + signed(handicap)

    def grade(value, *, ats_choice=False, model_line=False):
        labels = {'W': 'Covered', 'L': 'Not covered', 'PUSH': 'Push', 'PENDING': 'Pending',
                  'NOPICK': 'No edge' if ats_choice else 'No winner pick', 'NOEDGE': 'No edge',
                  'UNAVAILABLE': 'Unavailable'}
        if model_line:
            labels.update(W='Exceeded projection', L='Below projection', PUSH='Matched projection')
        if value not in labels:
            raise ValueError('Unknown saved ATS grade')
        return labels[value]

    unavailable = ats.get('unavailable', [])
    metrics = ats.get('metrics', {})
    records = []
    for key, label, skipped in (('model_line', 'Winner pick vs PGO projected line', 'no_pick'),
                                ('straight_up_ats', 'Winner pick vs sportsbook line', 'no_pick'),
                                ('ats', 'ATS suggestion vs sportsbook line', 'no_edge')):
        record = metrics.get(key, {})
        labels = ('Exceeded', 'Below', 'Matched') if key == 'model_line' else ('Wins', 'Losses', 'Pushes')
        counts = [(title, record.get(k, 0)) for title, k in zip(labels, ('wins', 'losses', 'pushes'))]
        counts += [('No edge' if skipped == 'no_edge' else 'No pick', record.get(skipped, 0)),
                   ('Pending', record.get('pending', 0)),
                   ('Unavailable', record.get('unavailable', 0 if key == 'model_line' else len(unavailable)))]
        records.append('<article class="game-day-card"><h4>' + label + '</h4><dl class="game-day-times">'
                       + ''.join('<div><dt>' + title + '</dt><dd>' + str(_integer(count)) + '</dd></div>' for title, count in counts)
                       + '</dl></article>')

    rows, details, seen = [], [], set()
    for game, available in [(g, True) for g in ats.get('games', [])] + [(g, False) for g in unavailable]:
        game_id = game['game_id']
        if game_id in seen:
            raise ValueError('Duplicate ATS display game ID')
        seen.add(game_id)
        key = _text(game_id)
        home, away = game.get('home'), game.get('away')
        matchup = _text(away) + ' @ ' + _text(home) if home and away else _text(game_id)
        projected = game.get('model_home_handicap')
        if projected is None and game.get('pgo_margin') is not None:
            projected = -_number(game['pgo_margin'])
        pgo_line = 'Unavailable' if projected is None else _text(home) + f' {_number(projected):+.1f}'
        grades = game.get('grade', {})
        model_grade = grade(grades.get('model_line', 'UNAVAILABLE'), model_line=True)
        provider = (game.get('provider') or ats.get('provider') or {}).get('name', 'Provider unavailable')
        if available:
            market = line(home, game['home_handicap']) + ' / ' + line(away, game['away_handicap'])
            market += '<br><small>' + _text(provider) + ' via ESPN</small>'
            status = game.get('status', 'CURRENT')
            status_label = {'CURRENT': 'Current saved line', 'STALE': 'Stale saved line', 'LOCKED': 'Locked line'}.get(status)
            if status_label is None:
                raise ValueError('Unknown saved ATS line status')
            market += '<br><small>' + status_label + '</small>'
            pick = game.get('ats_pick')
            if pick is None:
                choice = 'No projected ATS edge'
            else:
                if pick not in (home, away):
                    raise ValueError('ATS selection is outside the matchup')
                home_edge = _number(game['home_edge'])
                edge = home_edge if pick == home else -home_edge
                choice = line(pick, game['home_handicap'] if pick == home else game['away_handicap'])
                choice += '; edge ' + signed(edge) + ' NFL points'
            su_grade = grade(grades.get('straight_up_ats', 'PENDING'))
            ats_grade = grade(grades.get('ats', 'PENDING'), ats_choice=True)
            note = '<p>' + status_label + '. ' + _text(game.get('stale_reason') or '') + '</p>'
            clocks = [('Quote captured', game.get('quote_captured_at')), ('ATS selection issued', game.get('issued_at')),
                      ('Prediction lock', game.get('lock_at')), ('Kickoff', game.get('kickoff'))]
            note += '<dl>' + ''.join('<dt>' + label + '</dt><dd>' + _time(value) + '</dd>' for label, value in clocks) + '</dl>'
            source = game.get('source') or {}
            href = source.get('href')
            if href is None and source.get('path'):
                from pgo_season import archive_href
                href = archive_href(source['path'])
            if href:
                note += _sources([dict(href=href, label='Saved ESPN quote source')])
        else:
            market = 'Line unavailable'
            choice = ats_grade = su_grade = 'Unavailable'
            note = '<p>' + _text(game.get('reason') or 'No eligible pre-lock line was saved.') + '</p>'
        precise = 'Unavailable' if projected is None else _text(home) + f' {_number(projected):+}'
        note += '<p>Saved PGO projection at full precision: ' + precise + '.</p>'
        note += '<p>Original PGO prediction issued: ' + _time(game.get('pgo_issued_at')) + '. '
        note += 'Original PGO edition: ' + _text(game.get('source_edition') or 'Unavailable') + '.</p>'
        su_pick = game.get('su_pick')
        su_covered = (_text(su_pick) + ': ' if su_pick else '') + su_grade
        model_check = (_text(su_pick) + ': ' if su_pick else '') + model_grade
        rows.append([f'<a href="#season-ats-game-{key}" data-view-key="ats-link-{key}">{matchup}</a>',
                     pgo_line, model_check, market, su_covered, choice, ats_grade])
        details.append(f'<details id="season-ats-game-{key}" data-view-key="ats-game-{key}">'
                       f'<summary>{matchup}: saved line details</summary>{note}</details>')

    reason = ats.get('blocked_reason')
    status_note = '<p>Quote check: ' + _text(ats.get('status', 'Unavailable')) + '. Checked ' + _time(ats.get('checked_at')) + '.</p>'
    if reason:
        status_note += '<p>' + _text(reason) + '</p>'
    return ('<details class="model-update-evidence" id="season-ats" data-view-key="season-ats">'
            '<summary>PGO projected spreads and ATS results</summary>'
            '<p>A PGO projected line of LAR &minus;4.3 means the model expects the Rams to win by about 4.3 points. '
            'The table shows the home-team line: a minus sign favors the home team; a plus sign favors the away team. '
            'Sportsbook ATS grades use the saved DraftKings line supplied by ESPN.</p>'
            '<p>The PGO-line check says whether the winner pick exceeded, fell below or matched its projected margin. '
            'Exceeding the projection is not necessarily more accurate; margin error measures closeness. '
            'The table rounds the model line to one decimal, but checks use full precision, shown in saved line details. Close calls can differ from the rounded display.</p>'
            '<p>Straight-up picks win by any margin. Covering the spread requires the selected team to beat its saved handicap; '
            'an exact tie after applying the handicap is a push. The original straight-up W/L record stays unchanged.</p>'
            '<p>Quotes and ATS selections can refresh before T-60, one hour before kickoff. Grades use the last saved pre-lock line; '
            'stale quotes retain their original capture time. Missing sportsbook lines are excluded from sportsbook records; '
            'an authentic PGO forecast saved before lock can still receive a PGO-line check. '
            'No cover probability is estimated, and straight-up win chances are not cover chances.</p>'
            + status_note
            + '<div class="game-day-grid">' + ''.join(records) + '</div>'
            + '<p>Wins and losses count only graded selections. Pushes are listed separately, as are no-edge or no-pick games, pending games and unavailable lines.</p>'
            + (_test_table('ats-games', ['Matchup', 'PGO projected line (home)', 'Winner pick vs PGO line', 'ESPN sportsbook line',
                                       'Winner pick vs sportsbook line', 'PGO ATS choice', 'ATS result'], rows) if rows else '<p>No saved spread comparisons.</p>')
            + ''.join(details)
            + _sources([dict(href='https://www.espn.com/nfl/scoreboard', label='ESPN scoreboard; odds attributed to the saved provider')])
            + '</details>')
