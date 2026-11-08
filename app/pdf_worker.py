"""Bounded PDF subprocess: stdin bytes in, JSON page text out; no model or app startup."""
import json
import sys


def main():
    import resource
    # Apply limits before importing the native parser. Linux hosted containers enforce AS.
    resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024 * 1024, 2 * 1024 * 1024))
    if sys.platform.startswith("linux"):
        memory = int(sys.argv[3]) * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    import pymupdf
    max_pages, max_chars = int(sys.argv[1]), int(sys.argv[2])
    data = sys.stdin.buffer.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        return 1
    try:
        with pymupdf.open(stream=data, filetype="pdf") as pdf:
            if pdf.needs_pass or len(pdf) > max_pages:
                return 1
            pages, total = [], 0
            for number, page in enumerate(pdf):
                text = page.get_text()
                total += len(text)
                if total > max_chars:
                    return 1
                pages.append((number + 1, text))
        sys.stdout.write(json.dumps(pages))
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
