import time
from datetime import datetime, timezone


class BudgetExceeded(RuntimeError):
    pass


def reserve_model_call(store, settings):
    """Reserve before every attempt (including retries). Conservative call-based spend ceiling."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with store.connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS model_usage(day TEXT, actor TEXT, calls INTEGER, PRIMARY KEY(day, actor))")
        db.execute("DELETE FROM model_usage WHERE day < ?", (day,))
        for actor, limit in (("__global__", settings.daily_global_model_calls),
                             ("user:" + settings.actor_id, settings.daily_user_model_calls)):
            row = db.execute("SELECT calls FROM model_usage WHERE day=? AND actor=?", (day, actor)).fetchone()
            if row and row[0] >= limit:
                raise BudgetExceeded("Daily model request budget exhausted")
        for actor in ("__global__", "user:" + settings.actor_id):
            db.execute("INSERT INTO model_usage VALUES(?,?,1) ON CONFLICT(day,actor) DO UPDATE SET calls=calls+1", (day, actor))


def prune_expired(store, settings):
    import shutil
    store.cleanup(settings.retention_days)
    base = settings.data_dir / "experiments"
    if base.exists():
        cutoff = time.time() - settings.retention_days * 86400
        for entry in base.iterdir():
            if entry.is_dir() and not entry.is_symlink() and entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry)
    with store.connect() as db:
        if db.execute("SELECT name FROM sqlite_master WHERE name='sessions'").fetchone():
            db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
