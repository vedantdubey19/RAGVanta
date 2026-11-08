"""Administrator CLI. Passwords are entered privately and never passed as arguments."""
import argparse
import getpass
from app.auth import Auth
from app.config import Settings
from app.storage import Store

parser = argparse.ArgumentParser()
parser.add_argument("action", choices=["create", "disable", "reset-password"])
parser.add_argument("username")
args = parser.parse_args()
settings = Settings()
auth = Auth(Store(settings.data_dir), settings)
if args.action == "disable":
    auth.disable_user(args.username)
else:
    password = getpass.getpass("New password (14+ characters): ")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords do not match")
    if args.action == "create":
        auth.create_user(args.username, password)
    else:
        from app.auth import password_hash
        if not 14 <= len(password) <= 256:
            raise SystemExit("Password must contain 14–256 characters")
        with auth.store.connect() as db:
            if not db.execute("SELECT id FROM users WHERE id=?", (args.username,)).fetchone():
                raise SystemExit("Unknown user")
            db.execute("UPDATE users SET password=?,active=1 WHERE id=?", (password_hash(password), args.username))
            db.execute("DELETE FROM sessions WHERE user_id=?", (args.username,))
print("Account operation completed; existing sessions revoked when appropriate.")
