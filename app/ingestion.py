import hashlib
import json
import subprocess
import sys
import threading
from pathlib import Path


PDF_SLOTS = threading.BoundedSemaphore(1)

def extract(data, filename, settings):
    if not filename or Path(filename).name != filename or "\\" in filename or len(filename) > 180:
        raise ValueError("Invalid filename")
    if len(data) > settings.max_file_bytes:
        raise OverflowError("File exceeds upload limit")
    suffix = Path(filename).suffix.lower()
    if suffix == ".txt":
        if b"\x00" in data or data.startswith(b"%PDF"):
            raise ValueError("Expected UTF-8 text")
        try:
            pages = [(1, data.decode("utf-8"))]
        except UnicodeDecodeError as exc:
            raise ValueError("Expected UTF-8 text") from exc
    elif suffix == ".pdf" and data.startswith(b"%PDF-"):
        try:
            with PDF_SLOTS:
                worker = subprocess.run(
                    [sys.executable, "-m", "app.pdf_worker", str(settings.max_pages),
                     str(settings.max_text_chars), str(settings.pdf_memory_mb)], input=data, capture_output=True, timeout=10,
                    check=True, env={"PATH": "/usr/bin:/bin", "PYTHONUTF8": "1", "PYTHONNOUSERSITE": "1"})
            pages = json.loads(worker.stdout)
        except subprocess.TimeoutExpired as exc:
            raise ValueError("PDF extraction timeout") from exc
        except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
            raise ValueError("PDF rejected: malformed, encrypted, or over extraction limits") from exc
    else:
        raise ValueError("Only valid PDF and UTF-8 TXT files are supported")
    if sum(len(text) for _, text in pages) > settings.max_text_chars:
        raise OverflowError("Extracted text limit exceeded")
    if not any(text.strip() for _, text in pages):
        raise ValueError("Document contains no extractable text (OCR is not enabled)")
    return pages


def chunk_pages(pages, document_id, size, overlap):
    result = []
    for page, text in pages:
        for start in range(0, len(text), size - overlap):
            content = text[start:start + size]
            if content.strip():
                result.append({"id": f"{document_id}:{len(result):04d}", "page": page,
                               "start": start, "end": start + len(content), "text": content,
                               "sha256": hashlib.sha256(content.encode()).hexdigest()})
            if start + size >= len(text):
                break
    return result
