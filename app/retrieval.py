import hashlib
import math
import re
from collections import Counter


def tokens(text):
    return [word[:-1] if word.endswith("s") and len(word) > 3 else word
            for word in re.findall(r"\w+", text.lower())]


class Retriever:
    """Embedded, owner-scoped retrieval. No vector database server or remote-code loader."""
    def __init__(self, settings, store):
        self.settings, self.store = settings, store
        self.encoder = None
        self.identity = hashlib.sha256((settings.embedding_model + "@" + settings.embedding_revision).encode()).hexdigest()
        if settings.retrieval == "semantic":
            from sentence_transformers import SentenceTransformer
            self.encoder = SentenceTransformer(settings.embedding_model, revision=settings.embedding_revision,
                                               trust_remote_code=False)
            with store.connect() as db:
                db.execute("CREATE TABLE IF NOT EXISTS embeddings(id TEXT, model TEXT, vector BLOB, "
                           "PRIMARY KEY(id,model))")
            # Canonical chunks rebuild missing derived vectors; no external vector service.
            rows = store.query("SELECT chunks.* FROM chunks LEFT JOIN embeddings ON "
                               "embeddings.id=chunks.id AND embeddings.model=? WHERE embeddings.id IS NULL",
                               (self.identity,))
            self.index(rows)

    def index(self, chunks, db=None):
        if self.encoder is None or not chunks:
            return
        embeddings = self.encoder.encode([c["text"] for c in chunks], normalize_embeddings=True)
        values = [(chunk["id"], self.identity, vector.astype('float32').tobytes())
                  for chunk, vector in zip(chunks, embeddings)]
        if db is not None:
            db.executemany("INSERT OR REPLACE INTO embeddings VALUES(?,?,?)", values)
        else:
            with self.store.connect() as connection:
                connection.executemany("INSERT OR REPLACE INTO embeddings VALUES(?,?,?)", values)

    def delete(self, ids, db=None):
        if not ids:
            return
        if db is None:
            with self.store.connect() as connection:
                self.delete(ids, db=connection)
        elif db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='embeddings'").fetchone():
            # Remove cached vectors even if the operator switched back to lexical retrieval.
            db.executemany("DELETE FROM embeddings WHERE id=?", [(cid,) for cid in ids])

    def retrieve(self, question, collection_id, actor, top_k):
        access = self.store.query("SELECT id FROM collections WHERE id=? AND owner=?",
                                  (collection_id, actor))
        if not access:
            raise PermissionError("Collection unavailable")
        rows = self.store.query("SELECT chunks.*, documents.filename FROM chunks JOIN documents "
                                "ON documents.id=chunks.document_id WHERE chunks.collection_id=?",
                                (collection_id,))
        if not rows:
            return []
        if self.encoder is not None:
            import numpy as np
            # Only the authorized collection is read, even for the derived vector cache.
            vectors = self.store.query("SELECT embeddings.id,embeddings.vector FROM embeddings JOIN chunks "
                "ON chunks.id=embeddings.id JOIN collections ON collections.id=chunks.collection_id "
                "WHERE embeddings.model=? AND chunks.collection_id=? AND collections.owner=?",
                (self.identity, collection_id, actor))
            allowed = {row["id"]: row for row in rows}
            query = self.encoder.encode([question], normalize_embeddings=True)[0]
            scored = [dict(allowed[v["id"]], score=float(np.dot(query, np.frombuffer(v["vector"], dtype=np.float32))))
                      for v in vectors if v["id"] in allowed]
            return sorted(scored, key=lambda row: (-row["score"], row["id"]))[:top_k]
        query = Counter(tokens(question))
        scored = []
        for row in rows:
            words = Counter(tokens(row["text"]))
            score = sum(min(n, words[t]) for t, n in query.items())
            score /= math.sqrt(max(1, sum(words.values())))
            if score > 0:
                scored.append(dict(row, score=score))
        return sorted(scored, key=lambda r: (-r["score"], r["id"]))[:top_k]
