"""Local official browser login and server-side IAAA QR authorization."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import secrets
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
QR = None


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
                "loginMethod": "iaaa-qr" if REMOTE else "local-browser",
                "qrUrl": "/api/auth/qr?attempt=" + QR["id"] if QR and STATE["status"] == "waiting" else None}


def qr_image(attempt):
    with LOCK:
        if (not REMOTE or not QR or STATE["status"] != "waiting"
                or not secrets.compare_digest(attempt, QR["id"]) or time.monotonic() >= QR["deadline"]):
            return None
        return QR["image"]


def _start_qr():
    global QR
    from .iaaa import QRLogin
    with LOCK:
        if STATE["status"] in ("opening", "verifying", "logging_out"):
            raise ValueError("登录操作正在进行，请稍候。")
        if STATE["status"] == "waiting":
            return status()
        attempt = {"id": secrets.token_urlsafe(24), "cancel": threading.Event(),
                   "deadline": time.monotonic() + 180, "image": None}
        QR = attempt
        STATE.update(status="opening", message="正在向 IAAA 申请官方扫码二维码…")

    def run():
        global QR
        session = QRLogin()
        ticket = None
        try:
            image = session.begin()
            with LOCK:
                if attempt["cancel"].is_set() or QR is not attempt:
                    return
                attempt["image"] = image
                STATE.update(status="waiting", message="请使用北京大学 App 扫码，并在手机上确认登录教学网。二维码三分钟内有效。")
            while not attempt["cancel"].wait(3):
                ticket = session.poll()
                if ticket is None:
                    continue
                with LOCK:
                    if attempt["cancel"].is_set() or QR is not attempt:
                        return
                    attempt["image"] = None
                    STATE.update(status="verifying", message="扫码已确认，正在校验教学网与智云授权…")
                session.complete(ticket)
                ticket = None
                with LOCK:
                    STATE.update(status="done", message="扫码登录已通过校验，会话已加密保存。")
                return
        except Exception as error:
            with LOCK:
                if QR is attempt and not attempt["cancel"].is_set():
                    STATE.update(status="failed", message=str(error) if isinstance(error, auth.AuthError) else "扫码登录未完成，请重试。")
        finally:
            ticket = None
            session.close()
            with LOCK:
                attempt["image"] = None
                if QR is attempt:
                    QR = None
    threading.Thread(target=run, daemon=True).start()
    return status()


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
    if REMOTE:
        return _start_qr()
    def operation():
        _browser("--headed", "open", auth.HOME)
        with LOCK:
            STATE.update(status="waiting", message="请在独立窗口完成官方登录，再点击“已完成登录”。")
    return _job("opening", operation)


def finish():
    if REMOTE:
        raise ValueError("服务器使用 IAAA 扫码登录，手机确认后自动完成校验。")
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
        global QR
        with LOCK:
            if QR:
                QR["cancel"].set()
                QR["image"] = None
                QR = None
        # Remove only this project's encrypted campus state, not its database config.
        with auth._lock:
            auth.AUTH_FILE.unlink(missing_ok=True)
        if not REMOTE:
            try:
                _browser("close")
            except Exception:
                pass
        with LOCK:
            STATE.update(status="idle", message="课表软件已退出登录。离线课表仍可查询。")
    return _job("logging_out", operation)
