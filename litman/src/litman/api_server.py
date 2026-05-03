from __future__ import annotations

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from .models import Paper
from .store import get_members, member_root, load_all_papers, save_paper, find_duplicate

API_PORT = 51780

_started = False


def _collect_library_info() -> dict:
    members = get_members()
    papers = load_all_papers()

    lib_data: dict[str, list[str]] = {}
    for m in members:
        root = member_root(m)
        folder_prefix = f"folder:{root}/"
        folders: set[str] = set()
        for p in papers:
            for tag in p.tags:
                if tag.startswith(folder_prefix):
                    sub = tag[len(folder_prefix):]
                    folders.add(sub)
        lib_data[root] = sorted(folders, reverse=True)

    return lib_data


class _Handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/folders":
            self._send_json(200, _collect_library_info())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/papers":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
                doi = data.get("doi")
                url = data.get("url", "")
                dup = find_duplicate(doi, url) if doi else None
                if dup:
                    self._send_json(409, {"error": "duplicate", "id": dup.id, "title": dup.title})
                    return
                paper = Paper.model_validate(data)
                save_paper(paper)
                self._send_json(201, {"ok": True, "id": paper.id})
            except Exception as e:
                self._send_json(400, {"error": str(e)})
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        pass


def start_api_server():
    global _started
    if _started:
        return
    try:
        server = HTTPServer(("127.0.0.1", API_PORT), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        _started = True
    except OSError:
        pass
