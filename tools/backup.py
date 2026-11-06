"""SQLite online backup API; restore only while application is stopped."""
import argparse
import sqlite3
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('action', choices=['backup', 'restore'])
parser.add_argument('--mode', choices=['simulation', 'hardware'], required=True)
parser.add_argument('--data-dir', default='data')
parser.add_argument('--file', required=True)
parser.add_argument('--confirm-restore', action='store_true')
args = parser.parse_args()
live = Path(args.data_dir) / f'{args.mode}.sqlite3'
archive = Path(args.file)
if archive.resolve() == live.resolve():
    parser.error('Backup path must differ from live database')
if args.action == 'restore' and not args.confirm_restore:
    parser.error('Stop server first, then pass --confirm-restore')
source, target = (live, archive) if args.action == 'backup' else (archive, live)
if not source.is_file():
    parser.error('Source does not exist')
if args.action == 'backup' and target.exists():
    parser.error('Backup exists; choose a new file name')
target.parent.mkdir(parents=True, exist_ok=True)
with sqlite3.connect(f'file:{source.resolve()}?mode=ro', uri=True) as src:
    if src.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        parser.error('Source failed integrity check')
    with sqlite3.connect(target) as dst:
        src.backup(dst)
print(f'{args.action} completed: {target}')
