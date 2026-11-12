#!/usr/bin/env python3
"""Check or install complete LifeReview skill packages in Proma workspaces.

Read-only by default; --apply requires --backup-dir for recoverable updates.
The GitHub skills/ tree is the source, including references, evals and scripts.
"""
import argparse
import hashlib
from pathlib import Path
import shutil
import sys

SOURCE = Path(__file__).resolve().parents[1] / 'skills'
PACKAGES = {
    'lifereview-daily': 'lifereview-daily-20260701',
    'lifereview-weekly': 'lifereview-weekly-20260628',
    'lifereview-trajectory-map': 'lifereview-trajectory-map-20260808',
}


def files(folder):
    return {p.relative_to(folder): p for p in folder.rglob('*')
            if p.is_file() and '__pycache__' not in p.parts and p.name != '.DS_Store'}


def differences(source, target):
    expected, actual = files(source), files(target)
    return [str(name) for name in sorted(expected.keys() | actual.keys())
            if name not in expected or name not in actual or
            hashlib.sha256(expected[name].read_bytes()).digest() !=
            hashlib.sha256(actual[name].read_bytes()).digest()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', action='append', required=True,
                        help='Proma workspace root containing skills/; repeatable')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup-dir')
    args = parser.parse_args()
    if args.apply and not args.backup_dir:
        parser.error('--apply requires --backup-dir')
    pending = []
    for workspace in args.workspace:
        root = Path(workspace).expanduser().resolve()
        for source_name, installed_name in PACKAGES.items():
            source = SOURCE / source_name
            if not (source / 'SKILL.md').is_file():
                raise SystemExit(f'Incomplete source package: {source}')
            # Update all existing aliases; create the historical ID if absent.
            targets = [root / 'skills' / n for n in (installed_name, source_name)
                       if (root / 'skills' / n).exists()]
            for target in targets or [root / 'skills' / installed_name]:
                changed = differences(source, target)
                if not changed:
                    print(f'一致 {target}')
                    continue
                print(f'差异 {target}: ' + ', '.join(changed))
                pending.append((root, source, target))
    if args.apply:
        for root, source, target in pending:
            if target.is_symlink():
                raise SystemExit(f'Refuse to replace symlink: {target}')
            backup = Path(args.backup_dir).expanduser().resolve() / root.name / target.name
            if target.exists():
                if backup.exists():
                    raise SystemExit(f'Backup exists; choose a new backup directory: {backup}')
                shutil.copytree(target, backup, ignore=shutil.ignore_patterns('__pycache__'))
            # The whole old package is recoverable; stale files must not stay active.
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__'))
            if differences(source, target):
                raise SystemExit(f'Post-copy verification failed: {target}; backup: {backup}')
            print(f'已同步并校验 {target}')
        return 0
    return 1 if pending else 0


if __name__ == '__main__':
    sys.exit(main())
