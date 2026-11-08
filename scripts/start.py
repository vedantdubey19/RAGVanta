"""Render/container entry point. One worker preserves native index and concurrency invariants."""
import os
import uvicorn
from app.config import Settings

if __name__ == "__main__":
    os.umask(0o077)
    settings = Settings()
    uvicorn.run("app.main:app", host="0.0.0.0" if settings.deployment == "hosted" else "127.0.0.1",
                port=int(os.environ.get("PORT", "8000")), proxy_headers=False, workers=1,
                limit_concurrency=8, limit_max_requests=10000, timeout_keep_alive=5,
                access_log=False)
