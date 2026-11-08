"""Create an atomic SQLite backup. Target must be on operator-managed encrypted storage."""
import argparse
import os
import sqlite3
from pathlib import Path
from app.config import Settings

parser = argparse.ArgumentParser()
parser.add_argument("destination", type=Path)
args = parser.parse_args()
source = Settings().data_dir / "ragvanta.sqlite3"
args.destination.parent.mkdir(parents=True, exist_ok=True)
if args.destination.exists():
    raise SystemExit("Destination already exists")
fd = os.open(args.destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
os.close(fd)
with sqlite3.connect(source) as src, sqlite3.connect(args.destination) as target:
    src.backup(target)
print("Backup completed. Copy to encrypted off-host storage under the operator retention policy.")
