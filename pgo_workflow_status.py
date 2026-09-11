"""Report saved season health in Actions without suppressing blocked-state publication."""
import json
import os
from pathlib import Path


def report_health(state, summary_path=None):
    state = state or {}
    status = state.get('status', 'UNKNOWN')
    reason = state.get('blocked_reason')
    condition = 'READY' if status == 'READY' else 'UPDATE_REVIEW'
    for prefix, label in [('Waiting to publish the next week:', 'WAITING_FOR_NEXT_WEEK'),
                          ('Automatic update needs review:', 'SOURCE_REVIEW'),
                          ('Availability refresh needs review:', 'AVAILABILITY_REVIEW')]:
        if status != 'READY' and (reason or '').startswith(prefix):
            condition = label
    report = dict(status=status, condition=condition, blocked_reason=reason,
                  checked_at=state.get('checked_at'))
    components = [('penalty_shadow', 'penalty', 'READY'), ('totals_shadow', 'totals', 'READY'),
                  ('weights_shadow', 'weights', 'READY'),
                  ('replacement_depth', 'replacement_depth', 'DESCRIPTIVE / NOT IN MODEL'),
                  ('ats','ats','READY')]
    for key, prefix, _ in components:
        component = state.get(key) or {}
        report[prefix + '_status'] = component.get('status', 'UNKNOWN')
        report[prefix + '_blocked_reason'] = component.get('blocked_reason')
    report['replacement_depth_historical_admission'] = (state.get('replacement_depth') or {}).get('historical_admission')
    from pgo_season import availability_watch
    report['availability_watch'] = availability_watch(state)
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if summary_path:
        with Path(summary_path).open('a', encoding='utf-8') as handle:
            handle.write('### Saved PGO season health\n\n```json\n' + rendered + '\n```\n')
    warnings = []
    if status != 'READY':
        warnings.append(f'PGO {condition}: {reason or "Saved status is unavailable"}')
    for _, prefix, healthy in components:
        if report[prefix + '_status'] != healthy:
            warnings.append('PGO ' + prefix.replace('_', ' ') + ' monitor: '
                            + (report[prefix + '_blocked_reason'] or 'Saved status is unavailable'))
    watch = report['availability_watch']
    if watch.get('blocked_reason'):
        warnings.append('PGO final inactive watch: ' + watch['blocked_reason'])
    for game in watch['games']:
        if game['status'] in ('MISSING', 'STALE'):
            warnings.append(f'PGO final inactives {game["status"]}: {game["away"]} @ {game["home"]}; '
                            + 'missing teams: ' + (', '.join(game['missing_teams']) or 'none; check overdue')
                            + '; last observation: ' + (game.get('checked_at') or 'unavailable'))
    for warning in warnings:
        escaped = warning.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        print('::warning::' + escaped)
    return report


if __name__ == '__main__':
    from pgo_season import DEFAULT_ROOT, load_current
    report_health(load_current(DEFAULT_ROOT), os.environ.get('GITHUB_STEP_SUMMARY'))
