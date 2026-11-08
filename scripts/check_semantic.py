"""Opt-in integration check: downloads the configured public embedding model if uncached."""
import os
import tempfile
from pathlib import Path
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
os.environ.setdefault('HF_HOME', str(Path('.runtime/model-cache').resolve()))
from app.config import Settings
from app.service import Laboratory

with tempfile.TemporaryDirectory(prefix='ragvanta-semantic-') as directory:
    config = Settings(data_dir=Path(directory), retrieval='semantic', _env_file=None)
    lab = Laboratory(config)
    alice = lab.for_actor('alice')
    bob = lab.for_actor('bob')
    a = alice.create_collection('Alice policies')['id']
    b = bob.create_collection('Bob policies')['id']
    doc = alice.ingest(b'Returns are accepted within 7 days with a receipt.', 'policy.txt', a)
    hidden = bob.ingest(b'Returns are accepted within 99 days in the private collection.', 'private.txt', b)
    result = alice.answer('What is the return policy?', a)
    assert result['citations'] and result['citations'][0]['document_id'] == doc['id'], result
    assert all(not c['chunk_id'].startswith(hidden['id']) for c in result['retrieved'])
    try:
        alice.answer('What is the return policy?', b)
        raise AssertionError('Cross-user retrieval was not rejected')
    except PermissionError:
        pass
    print('Sentence Transformers + SQLite vector cache live integration passed: ingestion, retrieval, citations, and two-user isolation')
