"""Server-side password and revocable session authentication. No public registration."""
import hashlib
import hmac
import secrets
import time
import threading


COOKIE = "__Host-ragvanta_session"
CSRF_COOKIE = "ragvanta_csrf"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=131072, r=8, p=1,
                         maxmem=256 * 1024 * 1024)
    return salt + ":" + key.hex()


def password_matches(password, encoded):
    try:
        return hmac.compare_digest(password_hash(password, encoded.split(":")[0]), encoded)
    except (ValueError, TypeError):
        return False


class Auth:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings
        self.password_slots = threading.BoundedSemaphore(1)
        with store.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, password TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                csrf_hash TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS rate_buckets(key TEXT PRIMARY KEY, window INTEGER, count INTEGER);
            CREATE TABLE IF NOT EXISTS model_usage(day TEXT, actor TEXT, calls INTEGER,
                PRIMARY KEY(day, actor));
            ''')
        self.dummy_hash = password_hash(secrets.token_urlsafe(32))

    def create_user(self, username, password):
        import re
        if not re.fullmatch(r"[a-zA-Z0-9_.@-]{3,80}", username):
            raise ValueError("Username must contain 3–80 letters, digits, or _.@-")
        if not 14 <= len(password) <= 256:
            raise ValueError("Use a password containing 14–256 characters")
        with self.store.connect() as db:
            db.execute("INSERT INTO users VALUES(?,?,1,?)", (username, password_hash(password), time.time()))
        self.store.event("user_created", "accepted", {"user_id": username})

    def login(self, username, password):
        rows = self.store.query("SELECT * FROM users WHERE id=?", (username,))
        user = rows[0] if rows else None
        with self.password_slots:
            matches = password_matches(password, user["password"] if user else self.dummy_hash)
        if not matches or not user or not user["active"]:
            self.store.event("login", "denied", {})
            return None
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.store.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            db.execute("INSERT INTO sessions VALUES(?,?,?,?)", (digest(token), username, digest(csrf),
                       time.time() + self.settings.session_hours * 3600))
        self.store.event("login", "accepted", {"user_id": username})
        return token, csrf

    def session(self, token):
        if not token or len(token) > 200:
            return None
        rows = self.store.query("SELECT sessions.*,users.active FROM sessions JOIN users ON "
                                "users.id=sessions.user_id WHERE token_hash=? AND expires>? AND active=1",
                                (digest(token), time.time()))
        return rows[0] if rows else None

    def logout(self, token):
        with self.store.connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(token),))

    def rate(self, key, limit, seconds=60):
        window = int(time.time() // seconds)
        key = digest(key)
        with self.store.connect() as db:
            db.execute("DELETE FROM rate_buckets WHERE window < ?", (int(time.time() // seconds) - 2,))
            db.execute("INSERT INTO rate_buckets VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET "
                       "count=CASE WHEN window=excluded.window THEN count+1 ELSE 1 END, "
                       "window=excluded.window", (key, window))
            count = db.execute("SELECT count FROM rate_buckets WHERE key=?", (key,)).fetchone()[0]
        return count <= limit

    def disable_user(self, username):
        with self.store.connect() as db:
            db.execute("UPDATE users SET active=0 WHERE id=?", (username,))
            db.execute("DELETE FROM sessions WHERE user_id=?", (username,))
