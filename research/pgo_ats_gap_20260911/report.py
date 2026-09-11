"""Read-only descriptive ledger from a pinned season archive; output is exclusive."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import pgo_ats
import pgo_market_benchmark
from pgo_season import DEFAULT_ROOT, canonical, parse_scoreboard, require, utc

HERE = Path(__file__).resolve().parent


def pin(path):
    raw = path.read_bytes()
    return dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def run(root, archive, output, *, pointer_raw=None):
    """Replay exact archived quotes/finals and retain all inputs without mutation."""
    require(re.fullmatch(r'runs(?:-v2)?/\d{8}T\d{12}Z', archive) is not None, 'Invalid archive path')
    directory = root / archive
    pointer = dict(status='UNAVAILABLE', reason='Explicit archive replay; current pointer not used')
    if pointer_raw is not None:
        selected = json.loads(pointer_raw)
        require(selected['path'] == archive and pin(directory / 'manifest.json')['sha256'] == selected['manifest_sha256'],
                'Selected pointer and archive manifest differ')
        pointer = dict(status='CAPTURED', file='current.json', sha256=hashlib.sha256(pointer_raw).hexdigest(), bytes=len(pointer_raw))
    manifest = json.loads((directory / 'manifest.json').read_bytes())
    require(set(manifest['files']) in ({'state.json'}, {'state.json.gz'}), 'Invalid state inventory')
    filename = next(iter(manifest['files']))
    state_path = directory / filename
    require(pin(state_path) == manifest['files'][filename], 'State pin differs')
    raw = state_path.read_bytes()
    state = json.loads(gzip.decompress(raw) if filename.endswith('.gz') else raw)
    require(state['schema_version'] == 1 and state['season'] == 2026, 'Unexpected season state')
    checked = utc(state['checked_at'])
    tracked = [HERE / 'charter.md', HERE / 'charter-lock.json', Path(__file__),
               ROOT / 'pgo_market_benchmark.py', ROOT / 'tests/test_pgo_market_benchmark.py',
               ROOT / 'pgo_ats.py', ROOT / 'pgo_season.py', ROOT / 'pgo_season_accuracy.py',
               directory / 'manifest.json', state_path]
    lock = json.loads((HERE / 'charter-lock.json').read_bytes())
    require(pin(HERE / 'charter.md') == lock['charter'], 'Frozen charter changed')
    require(utc(lock['locked_at']) < datetime.now(timezone.utc), 'Charter freeze clock is in the future')
    cached = {}

    def replay(ref):
        path = root / ref['path']
        if path not in tracked:
            tracked.append(path)
        # _read checks each reference's digest, byte count, URL and capture clock.
        payload = pgo_ats._read(ref, root, checked)
        key = (ref['sha256'], ref['captured_at'])
        if key not in cached:
            cached[key] = (payload, parse_scoreboard(payload, state['schedule'], ref['captured_at']))
        return cached[key]

    for row in (state.get('ats') or {}).get('games', []):
        payload, parsed = replay(row['source'])
        metadata = parsed['events'][row['game_id']]
        require(metadata['event_id'] == row['event_id'], 'Quote event differs from captured bytes')
        event = next(event for event in payload['events'] if str(event['id']) == row['event_id'])
        require(pgo_ats._quote(event, row) == row['home_handicap'], 'Saved line differs from captured bytes')
    for result in state['results']:
        _, parsed = replay(result['source'])
        matches = [row for row in parsed['results'] if row['game_id'] == result['game_id']]
        require(len(matches) == 1 and all(result.get(key) == value for key, value in matches[0].items()),
                'Saved final differs from captured FINAL bytes')
    before = {str(path.relative_to(ROOT)): pin(path) for path in tracked}
    output.mkdir(parents=True, exist_ok=False)
    if pointer_raw is not None:
        (output / 'current.json').write_bytes(pointer_raw)
    receipt = dict(started_at=datetime.now(timezone.utc).isoformat(), archive=archive,
                   pointer=pointer,
                   state_checked_at=state['checked_at'], charter_locked_at=lock['locked_at'],
                   source_replay='Saved quote and explicit FINAL bytes replayed', inputs=before)
    (output / 'receipt.json').write_bytes(canonical(receipt))
    summary = pgo_market_benchmark.summarize(state)
    (output / 'summary.json').write_bytes(canonical(summary))
    require(before == {str(path.relative_to(ROOT)): pin(path) for path in tracked}, 'An input changed during evaluation')
    receipt['completed_at'] = datetime.now(timezone.utc).isoformat()
    receipt['inputs_unchanged'] = True
    (output / 'completion.json').write_bytes(canonical(receipt))
    inventory = {path.name: pin(path) for path in sorted(output.iterdir()) if path.is_file()}
    (output / 'manifest.json').write_bytes(canonical(dict(files=inventory)))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--archive', help='Pinned runs-v2 archive path; defaults to the verified current pointer')
    parser.add_argument('--output', type=Path, required=True, help='New directory; never overwrite a prior attempt')
    args = parser.parse_args()
    archive = args.archive
    pointer_raw = None
    if archive is None:
        pointer_raw = (args.root / 'current.json').read_bytes()
        pointer = json.loads(pointer_raw)
        archive = pointer['path']
    summary = run(args.root, archive, args.output, pointer_raw=pointer_raw)
    print(json.dumps(dict(benchmark=summary['benchmark'], ats=summary['ats'], prospective_status=summary['prospective_status']), indent=2))


if __name__ == '__main__':
    main()
