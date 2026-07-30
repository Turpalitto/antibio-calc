"""Local-only HTTP server for RC-030 owner review HTML and source PDFs.

The HTML directory and PDF directories remain separate. PDFs are exposed only
by bare filename under /__pdf__/<encoded-name>; directory traversal and
subpaths are rejected. Nothing is uploaded and no external network is used.
"""
from __future__ import annotations

import argparse
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


PDF_PREFIX = "/__pdf__/"


def resolve_pdf(url_path: str, pdf_roots: tuple[Path, ...]) -> Path | None:
    """Resolve one URL-encoded bare PDF filename within approved roots."""
    path = urlsplit(url_path).path
    if not path.startswith(PDF_PREFIX):
        return None
    filename = unquote(path[len(PDF_PREFIX) :])
    if (
        not filename
        or filename in {".", ".."}
        or Path(filename).name != filename
        or "/" in filename
        or "\\" in filename
        or not filename.casefold().endswith(".pdf")
    ):
        return None
    for root in pdf_roots:
        candidate = root / filename
        if candidate.is_file():
            return candidate
    return None


def make_handler(html_root: Path, pdf_roots: tuple[Path, ...]):
    class OwnerReviewHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(html_root), **kwargs)

        def send_head(self):
            if urlsplit(self.path).path.startswith(PDF_PREFIX):
                pdf = resolve_pdf(self.path, pdf_roots)
                if pdf is None:
                    self.send_error(404, "Source PDF not found in configured roots")
                    return None
                try:
                    handle = pdf.open("rb")
                except OSError:
                    self.send_error(404, "Source PDF cannot be opened")
                    return None
                stat = os.fstat(handle.fileno())
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(stat.st_size))
                encoded_name = self.path[len(PDF_PREFIX) :].split("?", 1)[0]
                self.send_header(
                    "Content-Disposition",
                    f"inline; filename*=UTF-8''{encoded_name}",
                )
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return handle
            return super().send_head()

    return OwnerReviewHandler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve RC-030 review UI and local source PDFs")
    parser.add_argument("--html-root", type=Path, required=True)
    parser.add_argument("--pdf-root", type=Path, action="append", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8977)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    html_root = args.html_root.resolve()
    pdf_roots = tuple(root.resolve() for root in args.pdf_root)
    if not html_root.is_dir():
        raise SystemExit(f"HTML root is not a directory: {html_root}")
    missing_roots = [root for root in pdf_roots if not root.is_dir()]
    if missing_roots:
        raise SystemExit(f"PDF root is not a directory: {missing_roots[0]}")

    server = ThreadingHTTPServer(
        (args.host, args.port),
        make_handler(html_root, pdf_roots),
    )
    print(
        f"RC-030 owner review: http://{args.host}:{args.port}/ "
        f"(HTML={html_root}; PDF roots={len(pdf_roots)})",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
