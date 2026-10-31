"""Loopback-only browser application; search never contacts campus services."""
from __future__ import annotations

import datetime as dt
import http.server
import json
from pathlib import Path
import threading
import urllib.parse
import uuid

from . import store
from .model import today

STATIC = Path(__file__).parent / "static"
JOBS = {}
LOCK = threading.Lock()


def launch_sync(day):
    with LOCK:
        if any(job["status"] == "running" for job in JOBS.values()):
            raise ValueError("已有同步任务正在运行，请等待完成。")
        job_id = uuid.uuid4().hex
        JOBS.clear()
        JOBS[job_id] = {"id": job_id, "status": "running", "message": "准备同步", "date": str(day)}
    def update(**values):
        with LOCK:
            JOBS[job_id].update(values)
    def run():
        try:
            from .sync import sync_day
            result = sync_day(day, lambda message: update(message=message))
            update(status="done", message="同步完成", result=result)
        except Exception as error:
            from .auth import AuthError
            message = str(error) if isinstance(error, (AuthError, ValueError, RuntimeError)) else "同步失败，请检查网络与数据库。"
            update(status="failed", message=message)
    threading.Thread(target=run, daemon=True).start()
    return {"id": job_id}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def local_request(self, write=False):
        port = self.server.server_port
        host = self.headers.get("Host", "")
        if host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
            return False
        return self.headers.get("Sec-Fetch-Site") != "cross-site"

    def send(self, status, body, mime="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False, default=self.json_value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass

    @staticmethod
    def json_value(value):
        if isinstance(value, (dt.date, dt.time, dt.datetime)):
            return value.isoformat()
        raise TypeError(type(value).__name__)

    def do_GET(self):
        if not self.local_request():
            return self.send(403, {"error": "仅允许本机同源访问。"})
        url = urllib.parse.urlsplit(self.path)
        query = {k: v[0] for k, v in urllib.parse.parse_qs(url.query, keep_blank_values=True).items()}
        try:
            if url.path == "/api/meta":
                return self.send(200, {**store.meta(), "today": today(), "application": "pku-classroom"})
            if url.path == "/api/auth/status":
                from . import login
                return self.send(200, login.status())
            if url.path == "/api/locations":
                return self.send(200, store.locations(query.get("term", "")))
            if url.path == "/api/search":
                return self.send(200, store.search(query))
            if url.path == "/api/job":
                with LOCK:
                    job = dict(JOBS.get(query.get("id"), {}))
                return self.send(200 if job else 404, job or {"error": "任务不存在。"})
            assets = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                      "/style.css": ("style.css", "text/css")}
            if url.path in assets:
                file, mime = assets[url.path]
                return self.send(200, (STATIC / file).read_bytes(), mime + "; charset=utf-8")
            return self.send(404, {"error": "页面不存在。"})
        except ValueError as error:
            return self.send(400, {"error": str(error)})
        except Exception:
            return self.send(503, {"error": "无法读取 PostgreSQL，请检查数据库配置与服务。"})

    def do_POST(self):
        if not self.local_request(write=True):
            return self.send(403, {"error": "仅允许本机同源访问。"})
        if self.path not in ("/api/sync", "/api/auth/login", "/api/auth/complete", "/api/auth/logout"):
            return self.send(404, {"error": "接口不存在。"})
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self.send(415, {"error": "需要 JSON 请求。"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 4096:
                raise ValueError("请求长度无效。")
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError("需要 JSON 对象。")
            if self.path.startswith("/api/auth/"):
                from . import login
                action = {"/api/auth/login": login.start, "/api/auth/complete": login.finish,
                          "/api/auth/logout": login.logout}[self.path]
                return self.send(202, action())
            day = dt.date.fromisoformat(body["date"])
            return self.send(202, launch_sync(day))
        except (ValueError, KeyError, TypeError) as error:
            return self.send(400, {"error": str(error) if isinstance(error, ValueError) else "日期无效。"})


def serve(port=8766):
    store.init_schema()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"教室查课：http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
