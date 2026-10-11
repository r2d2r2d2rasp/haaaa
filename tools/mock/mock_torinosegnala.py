"""Finto server TorinoSegnala per provare l'invio dalla UNO Q senza chiave e senza toccare il sito vero.

Imita le API v1 (docs/POD_API.md) con le stesse regole del server: chiave Bearer, categorie,
area di Torino, lotti di misure fino a 100. Stampa ogni richiesta.

    python tools/mock/mock_torinosegnala.py --port 3999 --key ts_live_prova
    # poi, per l'app:  TS_BASE_URL=http://127.0.0.1:3999 TS_API_KEY=ts_live_prova

--fail-every N  risponde 500 a una richiesta ogni N (per provare i nuovi tentativi)
"""
import argparse
import json
import re
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CATEGORIES = {"rifiuti_abbandonati", "cassonetto_pieno", "buca", "graffiti", "illuminazione", "altro"}
METRIC = re.compile(r"^[a-z0-9_]{1,32}$")


def in_turin(lat, lon):
    return isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and 44.9 <= lat <= 45.2 and 7.45 <= lon <= 7.9


def check_metrics(m):
    return isinstance(m, dict) and 0 < len(m) <= 30 and all(METRIC.match(k) and isinstance(v, (int, float)) for k, v in m.items())


def check_reading(r):
    if not isinstance(r, dict) or not check_metrics(r.get("metrics")):
        return "metrics"
    if ("lat" in r or "lon" in r) and not in_turin(r.get("lat"), r.get("lon")):
        return "lat/lon"
    return None


class Handler(BaseHTTPRequestHandler):
    key = ""
    fail_every = 0
    n = 0

    def do_POST(self):
        Handler.n += 1
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            body = json.loads(raw or b"null")
        except ValueError:
            body = None
        if self.headers.get("Authorization") != f"Bearer {self.key}":
            return self._send(401, {"error": "unauthorized"}, body)
        if self.fail_every and Handler.n % self.fail_every == 0:
            return self._send(500, {"error": "server_error"}, body)
        if self.path == "/api/v1/reports":
            if not isinstance(body, dict) or not in_turin(body.get("lat"), body.get("lon")):
                return self._send(422, {"error": "invalid_payload", "details": "lat/lon"}, body)
            if not 0 <= body.get("confidence", 1) <= 1:
                return self._send(422, {"error": "invalid_payload", "details": "confidence"}, body)
            if body.get("category") not in CATEGORIES:
                return self._send(422, {"error": "unknown_category"}, body)
            return self._send(201, {"id": str(uuid.uuid4()), "deduped": False}, body)
        if self.path == "/api/v1/readings":
            items = body.get("readings") if isinstance(body, dict) and "readings" in body else [body]
            if not isinstance(items, list) or not 1 <= len(items) <= 100:
                return self._send(422, {"error": "invalid_payload", "details": "readings"}, body)
            for r in items:
                if err := check_reading(r):
                    return self._send(422, {"error": "invalid_payload", "details": err}, body)
            return self._send(201, {"stored": len(items)}, body)
        if self.path == "/api/v1/heartbeat":
            return self._send(200, {"ok": True}, body)
        return self._send(404, {"error": "not_found"}, body)

    def _send(self, status, obj, body):
        shown = dict(body) if isinstance(body, dict) else body
        if isinstance(shown, dict) and "photo_base64" in shown:
            shown["photo_base64"] = f"[foto {len(shown['photo_base64']) * 3 // 4 // 1024} KB]"
        if isinstance(shown, dict) and "readings" in shown:
            shown = {"readings": f"[{len(shown['readings'])} misure]", "prima": shown["readings"][0]}
        print(f"{status} {self.path} {json.dumps(shown, ensure_ascii=False)[:300]}", flush=True)
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=3999)
    p.add_argument("--key", default="ts_live_prova")
    p.add_argument("--fail-every", type=int, default=0)
    a = p.parse_args()
    Handler.key, Handler.fail_every = a.key, a.fail_every
    print(f"finto TorinoSegnala su http://127.0.0.1:{a.port} (chiave {a.key})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()
