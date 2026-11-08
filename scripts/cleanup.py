"""Remove expired metadata and isolated experiment corpora, never operator documents."""
import shutil
import time
from app.config import Settings
from app.storage import Store

settings = Settings()
store = Store(settings.data_dir)
store.cleanup(settings.retention_days)
base = settings.data_dir / "experiments"
cutoff = time.time() - settings.retention_days * 86400
if base.exists():
    for directory in base.iterdir():
        if directory.is_dir() and not directory.is_symlink() and directory.stat().st_mtime < cutoff:
            shutil.rmtree(directory)
print("Expired run metadata, audit events, and experiment fixtures cleaned.")
