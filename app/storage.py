import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager


class Store:
    def __init__(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
        self.path = directory / "ragvanta.sqlite3"
        self.lock = threading.RLock()
        with self.connect() as db:
            for attempt in range(5):
                try:
                    db.execute("PRAGMA journal_mode=WAL")
                    break
                except sqlite3.OperationalError:
                    if attempt == 4:
                        raise
                    time.sleep(0.1 * (attempt + 1))
            db.executescript('''
            CREATE TABLE IF NOT EXISTS collections(id TEXT PRIMARY KEY, owner TEXT, name TEXT);
            CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, collection_id TEXT,
                filename TEXT, sha256 TEXT, created REAL, pages INTEGER, settings TEXT);
            CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY, document_id TEXT,
                collection_id TEXT, page INTEGER, start INTEGER, end INTEGER, text TEXT);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, owner TEXT, created REAL,
                status TEXT, report TEXT);
            CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, created REAL, operation TEXT,
                outcome TEXT, details TEXT);
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=15)
            db.row_factory = sqlite3.Row
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

    def query(self, sql, params=()):
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, params).fetchall()]

    def event(self, operation, outcome, details):
        with self.connect() as db:
            db.execute("INSERT INTO events VALUES(?,?,?,?,?)",
                       (uuid.uuid4().hex, time.time(), operation, outcome, json.dumps(details)))

    def cleanup(self, days):
        cutoff = time.time() - days * 86400
        with self.connect() as db:
            db.execute("DELETE FROM runs WHERE created < ?", (cutoff,))
            db.execute("DELETE FROM events WHERE created < ?", (cutoff,))
