"""Create an idempotent local synthetic demo collection. Does not overwrite user documents."""
from pathlib import Path
from app.config import Settings
from app.service import Laboratory

lab = Laboratory(Settings())
name = "Demo · Synthetic Support Policies"
existing = lab.store.query("SELECT id FROM collections WHERE name=? AND owner=?", (name, lab.settings.actor_id))
if existing:
    collection_id = existing[0]["id"]
else:
    collection_id = lab.create_collection(name)["id"]
    source = Path(__file__).resolve().parents[1] / "datasets/safe_documents/support-policy.txt"
    lab.ingest(source.read_bytes(), source.name, collection_id)
print(f"Demo collection ready: {collection_id}")
