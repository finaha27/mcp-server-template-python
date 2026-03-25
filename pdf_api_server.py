"""
Standalone PDF API server.

This service contains all PDF-reading and text extraction logic.
"""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pypdf import PdfReader

DOCS_DIR = Path(__file__).resolve().parent / "docs"


def _split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", normalized) if s.strip()]


def _count_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def _analyze_lecture_pdf(lecture_number: int) -> dict[str, str | int]:
    filename = f"MachineLearning-Lecture{lecture_number:02d}.pdf"
    pdf_path = DOCS_DIR / filename

    if not pdf_path.is_file():
        raise FileNotFoundError(f"Lecture PDF not found: {filename}")

    reader = PdfReader(str(pdf_path))
    full_text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if not full_text:
        raise ValueError(f"No readable text found in {filename}")

    sentences = _split_sentences(full_text)
    if not sentences:
        raise ValueError(f"Could not detect sentences in {filename}")

    return {
        "lecture_number": lecture_number,
        "file_name": filename,
        "word_count": _count_words(full_text),
        "first_sentence": sentences[0],
        "last_sentence": sentences[-1],
    }


class PDFAPIRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        if parsed_url.path != "/lecture-summary":
            self._write_json(404, {"error": "Not found"})
            return

        query_params = parse_qs(parsed_url.query)
        lecture_values = query_params.get("lecture_number")
        if not lecture_values:
            self._write_json(400, {"error": "Missing query parameter: lecture_number"})
            return

        try:
            lecture_number = int(lecture_values[0])
            if lecture_number < 1:
                raise ValueError("lecture_number must be >= 1")
        except ValueError as exc:
            self._write_json(400, {"error": f"Invalid lecture_number: {exc}"})
            return

        try:
            payload = _analyze_lecture_pdf(lecture_number)
            self._write_json(200, payload)
        except FileNotFoundError as exc:
            self._write_json(404, {"error": str(exc)})
        except Exception as exc:  # pragma: no cover
            self._write_json(500, {"error": str(exc)})

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _write_json(self, status_code: int, payload: dict[str, str | int]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_pdf_api_server(host: str = "127.0.0.1", port: int = 8001) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), PDFAPIRequestHandler)


def start_pdf_api_server_in_thread(
    host: str = "127.0.0.1", port: int = 8001
) -> ThreadingHTTPServer:
    server = create_pdf_api_server(host=host, port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="pdf-api-server")
    thread.start()
    return server


def run_pdf_api_server(host: str = "127.0.0.1", port: int = 8001) -> None:
    server = create_pdf_api_server(host=host, port=port)
    server.serve_forever()
