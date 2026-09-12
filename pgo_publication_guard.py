"""Allow a tested board publisher to consume only newer mutable season files."""
import argparse
import json
import re
import subprocess
from pathlib import Path


def check_publication(tested_sha, root=Path('.')):
    if not re.fullmatch(r'[0-9a-f]{40}', tested_sha):
        raise ValueError('A full tested commit SHA is required')

    def git(*args):
        try:
            return subprocess.check_output(['git', *args], cwd=root,
                                           stderr=subprocess.PIPE).decode('utf-8')
        except subprocess.CalledProcessError as error:
            raise ValueError('Cannot verify publication history') from error

    tested = git('rev-parse', '--verify', tested_sha + '^{commit}').strip()
    latest = git('rev-parse', 'HEAD').strip()
    ancestor = subprocess.run(['git', 'merge-base', '--is-ancestor', tested, latest],
                              cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if ancestor.returncode:
        raise ValueError('Tested commit must be an ancestor of publication HEAD')
    # Inspect both sides of renames so a move cannot hide a frozen-file deletion.
    fields = git('diff', '--name-status', '-z', '--no-renames',
                 tested, latest, '--').split('\0')[:-1]
    changes = list(zip(fields[::2], fields[1::2]))
    mutable = ('docs/index.html', 'docs/forecast-lab.html',
               'docs/evidence/season-2026/current.json')
    archives = tuple('docs/evidence/season-2026/' + folder + '/' for folder in
                     ('runs', 'runs-v2', 'availability', 'availability-v2', 'sources', 'source-archive',
                      'injury-usage/targets', 'injury-usage/reports', 'offensive-usage/reports'))
    forbidden = [path for status, path in changes
                 if not (status in ('A', 'M') and path in mutable)
                 and not (status == 'A' and path.startswith(archives))]
    if forbidden:
        raise ValueError('Untested changes require a new passing run: ' + ', '.join(forbidden))
    return dict(tested_sha=tested, publication_sha=latest,
                mutable_files=[path for _, path in changes])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tested_sha')
    args = parser.parse_args()
    try:
        print(json.dumps(check_publication(args.tested_sha), indent=2))
    except ValueError as error:
        raise SystemExit(str(error))


if __name__ == '__main__':
    main()
