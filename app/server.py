"""Tiny demo service that exposes Prometheus metrics, using only the standard library.

Endpoints:
  /work     simulated work, fails with HTTP 500 for a fraction of requests (FAIL_RATE)
  /healthz  liveness check, not counted in the metrics
  /metrics  Prometheus text exposition format, not counted in the metrics
"""
import json
import os
import random
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8000"))
FAIL_RATE = float(os.environ.get("FAIL_RATE", "0.2"))
BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)
KNOWN_PATHS = {"/work"}  # anything else is labelled "other", so label values cannot grow without bound
QUIET_PATHS = {"/healthz", "/metrics"}


class Metrics:
    def __init__(self):
        self.lock = threading.Lock()
        self.requests = {}  # (path, status) -> count
        self.latency = {}   # path -> [cumulative bucket counts, sum, count]

    def observe(self, path, status, seconds):
        with self.lock:
            key = (path, str(status))
            self.requests[key] = self.requests.get(key, 0) + 1
            hist = self.latency.setdefault(path, [[0] * len(BUCKETS), 0.0, 0])
            for i, bound in enumerate(BUCKETS):
                if seconds <= bound:
                    hist[0][i] += 1
            hist[1] += seconds
            hist[2] += 1

    def render(self):
        lines = [
            "# HELP http_requests_total Requests handled, by path and status code.",
            "# TYPE http_requests_total counter",
        ]
        with self.lock:
            for (path, status), n in sorted(self.requests.items()):
                lines.append(f'http_requests_total{{path="{path}",status="{status}"}} {n}')
            lines += [
                "# HELP http_request_duration_seconds Request latency in seconds.",
                "# TYPE http_request_duration_seconds histogram",
            ]
            for path, (counts, total, n) in sorted(self.latency.items()):
                for bound, c in zip(BUCKETS, counts):
                    lines.append(f'http_request_duration_seconds_bucket{{path="{path}",le="{bound}"}} {c}')
                lines.append(f'http_request_duration_seconds_bucket{{path="{path}",le="+Inf"}} {n}')
                lines.append(f'http_request_duration_seconds_sum{{path="{path}"}} {total}')
                lines.append(f'http_request_duration_seconds_count{{path="{path}"}} {n}')
        return "\n".join(lines) + "\n"


METRICS = Metrics()


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, content_type="application/json"):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            return self._send(200, "ok", "text/plain")
        if path == "/metrics":
            return self._send(200, METRICS.render(), "text/plain; version=0.0.4")
        start = time.perf_counter()
        if path == "/work":
            time.sleep(random.uniform(0.005, 0.15))
            if random.random() < FAIL_RATE:
                status, body = 500, json.dumps({"error": "simulated failure"})
            else:
                status, body = 200, json.dumps({"ok": True})
        else:
            status, body = 404, json.dumps({"error": "not found"})
        label = path if path in KNOWN_PATHS else "other"
        METRICS.observe(label, status, time.perf_counter() - start)
        self._send(status, body)

    def log_message(self, fmt, *args):
        if self.path.split("?", 1)[0] not in QUIET_PATHS:
            super().log_message(fmt, *args)


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    # As PID 1 the process gets no default SIGTERM behaviour, so stop cleanly on purpose.
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown).start())
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
