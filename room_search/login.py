"""Independent visible official login; browser cookies stay in memory until encrypted."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

from . import auth
from .paths import ROOT

SESSION = "pku-classroom-login-" + hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
LOCK = threading.RLock()
STATE = {"status": "idle", "message": "同步课表前，请在本软件单独登录教学网。"}
REMOTE = os.environ.get("PKU_CLASSROOM_REMOTE_LOGIN") == "1"


def _browser(*arguments):
    command = "agent-browser.cmd" if os.name == "nt" else "agent-browser"
    local = ROOT / ".tools/node_modules/.bin" / command
    bundled = Path(getattr(sys, "_MEIPASS", ROOT)) / "tools/agent-browser-win32-x64.exe"
    executable = str(bundled) if getattr(sys, "frozen", False) and bundled.is_file() else str(local) if local.is_file() else shutil.which(command)
    if not executable:
        raise RuntimeError("未找到已安装的 agent-browser；离线查询仍可使用。")
    capture = arguments[:2] in (("cookies", "get"), ("get", "url"))
    # A newly spawned browser daemon can inherit output handles. Open/close do
    # not need output: DEVNULL lets the CLI exit without waiting for daemon EOF.
    options = []
    configured_browser = os.environ.get("PKU_CLASSROOM_BROWSER_EXECUTABLE")
    if configured_browser:
        options = ["--executable-path", configured_browser]
    if getattr(sys, "frozen", False) and os.name == "nt":
        browsers = [Path(os.environ.get(name, "C:/")) / relative for name, relative in (
            ("PROGRAMFILES(X86)", "Microsoft/Edge/Application/msedge.exe"),
            ("PROGRAMFILES", "Microsoft/Edge/Application/msedge.exe"),
            ("PROGRAMFILES", "Google/Chrome/Application/chrome.exe"),
            ("LOCALAPPDATA", "Google/Chrome/Application/chrome.exe"))]
        browser = next((path for path in browsers if path.is_file()), None)
        if browser:
            options = ["--executable-path", str(browser)]
    result = subprocess.run([executable, "--session", SESSION, *options, *arguments],
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        encoding="utf-8", errors="replace", timeout=45,
        env={k: v for k, v in os.environ.items() if not k.startswith("AGENT_BROWSER_")},
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if result.returncode:
        # CLI output may contain page URLs/cookies; never include it in errors/logs.
        raise RuntimeError("独立登录浏览器操作失败，请重试并检查校园网。")
    return result.stdout or ""


def status():
    with LOCK:
        return {**STATE, "auth": auth.auth_status(), "independent": True, "remoteLogin": REMOTE,
                "loginUrl": "/admin/desktop/vnc.html?autoconnect=1&resize=scale&path=admin/desktop/websockify" if REMOTE else None}


def _job(phase, operation):
    with LOCK:
        if STATE["status"] in ("opening", "verifying", "logging_out"):
            raise ValueError("登录操作正在进行，请稍候。")
        STATE.update(status=phase, message="正在打开独立登录窗口…" if phase == "opening" else "正在验证官方登录…")

    def run():
        try:
            operation()
        except Exception as error:
            message = str(error) if isinstance(error, (auth.AuthError, RuntimeError, ValueError)) else "登录未完成，请重试。"
            with LOCK:
                STATE.update(status="failed", message=message)
    threading.Thread(target=run, daemon=True).start()
    return status()


def start():
    with LOCK:
        if REMOTE and STATE["status"] == "waiting":
            return status()
    def operation():
        _browser("--headed", "open", auth.HOME)
        with LOCK:
            STATE.update(status="waiting", message="请在弹窗中完成官方登录，校验通过后自动保存并同步。" if REMOTE else
                         "请在独立窗口完成官方登录，再点击“已完成登录”。")
        if REMOTE:
            threading.Thread(target=_watch_login, daemon=True).start()
    return _job("opening", operation)


def _watch_login():
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        time.sleep(3)
        with LOCK:
            if STATE["status"] != "waiting":
                return
        try:
            url = _browser("get", "url").strip()
            if url.startswith("https://course.pku.edu.cn/webapps/portal/"):
                finish()
                return
        except Exception:
            continue
    with LOCK:
        if STATE["status"] != "waiting":
            return
        STATE.update(status="failed", message="登录窗口已超时，请重新打开登录。")
    try:
        _browser("close")
    except Exception:
        pass


def finish():
    def operation():
        data = json.loads(_browser("cookies", "get", "--json"))
        payload = data.get("data", {})
        cookies = payload.get("cookies") if isinstance(payload, dict) else payload
        if not data.get("success") or not isinstance(cookies, list):
            raise ValueError("独立浏览器没有返回有效会话，请先完成官方登录。")
        auth.import_browser_cookies(cookies)
        with LOCK:
            STATE.update(status="done", message="已独立登录并通过智云校验；可同步所选日期。")
        try:
            _browser("close")
        except Exception:
            pass
    return _job("verifying", operation)


def logout():
    def operation():
        # Remove only this project's encrypted campus state, not its database config.
        with auth._lock:
            auth.AUTH_FILE.unlink(missing_ok=True)
        try:
            _browser("close")
        except Exception:
            pass
        with LOCK:
            STATE.update(status="idle", message="课表软件已退出登录。离线课表仍可查询。")
    return _job("logging_out", operation)
