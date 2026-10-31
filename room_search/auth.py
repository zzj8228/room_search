"""Account-scoped official PKU SSO and current-user DPAPI session storage."""
from __future__ import annotations

import base64
import ctypes
import datetime as dt
import http.cookiejar
import json
import os
from pathlib import Path
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from .paths import runtime_dir

AUTH_FILE = runtime_dir() / "auth/pku-browser-state.dpapi"
HOME = "https://course.pku.edu.cn/webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_1_1"
VIDEO_BASE = "https://course.pku.edu.cn/webapps/bb-streammedia-hqy-BBLEARN/"
SSO_HOSTS = {"course.pku.edu.cn", "yjapise.pku.edu.cn", "onlineroomse.pku.edu.cn", "iaaa.pku.edu.cn"}
_lock = threading.RLock()


class AuthError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def dpapi(data: bytes, decrypt=False) -> bytes:
    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_uint32), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    if decrypt:
        operation = crypt.CryptUnprotectData
        operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(Blob)]
        ok = operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    else:
        operation = crypt.CryptProtectData
        operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_wchar_p, ctypes.c_void_p,
                              ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(Blob)]
        ok = operation(ctypes.byref(source), "PKU Classroom browser session", None, None, None, 1, ctypes.byref(target))
    if not ok:
        raise AuthError("session_unreadable", "无法解密或保存登录态，请以保存会话的 Windows 用户运行应用。")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


def load_state(path=None):
    path = path or AUTH_FILE
    try:
        return json.loads(dpapi(bytes.fromhex(path.read_text(encoding="ascii").strip()), decrypt=True).decode("utf-16-le"))
    except FileNotFoundError:
        raise AuthError("login_required", "未找到加密会话，请先登录北大教学网并保存会话。") from None
    except (OSError, ValueError, UnicodeError):
        raise AuthError("session_unreadable", "无法读取加密会话，请以保存会话的 Windows 用户运行应用。") from None


def save_state(state, path=None):
    path = path or AUTH_FILE
    # Only encrypted bytes ever reach disk; replace keeps the previous state on failure.
    encrypted = dpapi(json.dumps(state, ensure_ascii=False).encode("utf-16-le")).hex()
    temporary = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(encrypted, encoding="ascii")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def pku_domain(domain):
    domain = str(domain).lstrip(".").lower()
    return domain == "pku.edu.cn" or domain.endswith(".pku.edu.cn")


def extract_token(cookies):
    for cookie in cookies:
        if cookie.get("name") != "_token" or not pku_domain(cookie.get("domain", "")):
            continue
        match = re.search(r'i:1;s:\d+:"([^"]+)"', urllib.parse.unquote(cookie.get("value", "")))
        token = match.group(1) if match else cookie.get("value", "")
        if re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token):
            expires = cookie.get("expires", -1)
            if isinstance(expires, (int, float)) and expires > 0 and expires <= time.time() + 60:
                continue
            try:
                payload = token.split(".")[1]
                exp = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))).get("exp")
                if not isinstance(exp, (int, float)) or exp <= time.time() + 60:
                    continue
            except (ValueError, KeyError, TypeError):
                continue
            return token
    return None


class OfficialRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlparse(newurl)
        if target.scheme != "https" or target.hostname not in SSO_HOSTS or target.port not in (None, 443):
            raise AuthError("unexpected_redirect", "官方登录跳转到了未支持的地址，已停止；请在官方网页完成授权。")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def cookie_jar(state):
    jar = http.cookiejar.CookieJar()
    for item in state.get("cookies", []):
        if not pku_domain(item.get("domain", "")):
            continue
        expires = item.get("expires")
        expires = int(expires) if isinstance(expires, (int, float)) and expires > 0 else None
        jar.set_cookie(http.cookiejar.Cookie(
            version=0, name=item["name"], value=item["value"], port=None, port_specified=False,
            domain=item["domain"], domain_specified=item["domain"].startswith("."),
            domain_initial_dot=item["domain"].startswith("."), path=item.get("path", "/"), path_specified=True,
            secure=item.get("secure", True), expires=expires, discard=expires is None,
            comment=None, comment_url=None, rest={"HttpOnly": item.get("httpOnly", False)}, rfc2109=False))
    return jar


def jar_state(jar, state):
    cookies = [c for c in state.get("cookies", []) if not pku_domain(c.get("domain", ""))]
    for c in jar:
        cookies.append({"name": c.name, "value": c.value, "domain": c.domain, "path": c.path,
                        "expires": c.expires if c.expires is not None else -1, "secure": c.secure,
                        "httpOnly": c.has_nonstandard_attr("HttpOnly"), "sameSite": "Lax"})
    return {**state, "cookies": cookies}


def acquire_token(force=False):
    with _lock:
        return _acquire_token(load_state(), force)


def _acquire_token(state, force=False):
    """Verify candidate cookies before replacing the last working encrypted state."""
    with _lock:
        token = extract_token(state.get("cookies", []))
        if token and not force:
            return token
        jar = cookie_jar(state)
        if force:
            for cookie in list(jar):
                if cookie.name == "_token":
                    jar.clear(cookie.domain, cookie.path, cookie.name)
        opener = urllib.request.build_opener(OfficialRedirects(), urllib.request.HTTPCookieProcessor(jar))
        deadline = time.monotonic() + 75
        def fetch(url):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AuthError("network_error", "官方 SSO 超时，请检查校园网及代理后重试。")
            url = urllib.parse.quote(url, safe=":/?&=+%#;,@~-._")
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml,*/*"})
            with opener.open(request, timeout=min(20, remaining)) as response:
                target = urllib.parse.urlparse(response.url)
                if target.hostname == "iaaa.pku.edu.cn" or target.path.startswith("/webapps/login"):
                    raise AuthError("login_required", "教学网会话已过期，请在官方页面重新登录。")
                return response.read(8 * 1024 * 1024).decode("utf-8", errors="replace")
        try:
            home = fetch(HOME).replace("&amp;", "&")
            course_ids = list(dict.fromkeys(re.findall(r"(?:course_id=|key=)(_\d+_1)", home)))
            if not course_ids:
                raise AuthError("login_required", "教学网未返回本人课程，请在官方页面重新登录或授权。")
            play_token = None
            failed_courses = 0
            for course_id in course_ids:
                try:
                    page = fetch(VIDEO_BASE + "videoList.action?" + urllib.parse.urlencode({"course_id": course_id, "mode": "view"}))
                except urllib.error.URLError:
                    failed_courses += 1
                    continue
                match = re.search(r"playVideo\.action\?token=([A-Za-z0-9._-]+)", page.replace("&amp;", "&"))
                if match:
                    play_token = match.group(1)
                    break
            if not play_token:
                if failed_courses:
                    raise AuthError("network_error", "部分本人课程入口请求失败，尚未建立智云登录；请检查网络后重试。")
                raise AuthError("no_sso_entry", "本人可见课程中没有返回官方回放入口，无法建立智云 SSO。")
            page = fetch(VIDEO_BASE + "playVideo.action?" + urllib.parse.urlencode({"token": play_token})).replace("&amp;", "&")
            match = re.search(r'https://yjapise\.pku\.edu\.cn/casapi/index\.php\?[^\s"\'<>]+', page)
            if not match:
                raise AuthError("sso_entry_missing", "官方回放页面没有返回智云 SSO 地址。")
            fetch(match.group(0))
        except (urllib.error.URLError, TimeoutError, OSError, UnicodeError):
            raise AuthError("network_error", "无法连接教学网或智云 SSO，请检查校园网及代理后重试。") from None
        updated = jar_state(jar, state)
        token = extract_token(updated["cookies"])
        if not token:
            raise AuthError("authorization_required", "官方 SSO 未签发有效智云令牌，请在官方网页完成登录或授权。")
        verify_token(token)
        save_state(updated)
        return token


def verify_token(token):
    """Check server-side validity using the same official API used for search."""
    query = urllib.parse.urlencode({"search_time": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat(), "tenant": 226,
        "unique_course": 1, "with_sub_data": 1, "need_time_quantum": 1,
        "with_sub_duration": 1, "course_student_type": "", "sub_live_status": ""})
    request = urllib.request.Request(
        "https://onlineroomse.pku.edu.cn/courseapi/v2/course-live/search-live-course-list?" + query,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json",
                 "Referer": "https://onlineroomse.pku.edu.cn/", "User-Agent": "Mozilla/5.0 PKUClassroom/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read(8 * 1024 * 1024).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise AuthError("session_rejected", "智云服务拒绝当前登录会话，请重新登录或授权。") from None
        raise AuthError("network_error", f"登录校验接口返回 HTTP {exc.code}，请检查校园网或稍后重试。") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise AuthError("network_error", "无法在线校验登录状态，请检查校园网及代理后重试。") from None
    except (ValueError, UnicodeError):
        raise AuthError("invalid_response", "登录校验未返回有效数据，请检查校园网及代理。") from None
    if not isinstance(data, dict) or "code" not in data:
        raise AuthError("invalid_response", "登录校验响应格式异常，尚未确认登录有效。")
    if data["code"] != 0:
        raise AuthError("session_rejected", "智云接口未接受当前登录会话，请重新登录或检查账号授权。")
    if not isinstance(data.get("list"), list):
        raise AuthError("invalid_response", "登录校验未返回课程目录字段，尚未确认登录有效。")


def auth_status(ensure=False):
    saved = False
    try:
        state = load_state()
        saved = True
        token = acquire_token() if ensure else extract_token(state.get("cookies", []))
        if ensure:
            try:
                verify_token(token)
            except AuthError as exc:
                if exc.code != "session_rejected":
                    raise
                token = acquire_token(force=True)
                verify_token(token)
        return {"saved": True, "token": bool(token), "cookieCount": len(state.get("cookies", [])),
                "verified": bool(token) and ensure,
                "message": "已登录 · 在线校验通过" if token and ensure else "已保存会话，尚未在线校验"}
    except AuthError as exc:
        return {"saved": saved, "token": False, "verified": False, "code": exc.code, "message": str(exc)}


def import_browser_cookies(cookies):
    """Accept a native browser snapshot, verify SSO, then persist encrypted state."""
    if not isinstance(cookies, list) or len(cookies) > 1000:
        raise AuthError("invalid_cookies", "浏览器会话格式无效。")
    filtered = []
    for cookie in cookies:
        if not isinstance(cookie, dict) or not all(isinstance(cookie.get(key), str) for key in ("name", "value", "domain")):
            raise AuthError("invalid_cookies", "浏览器会话格式无效。")
        if not pku_domain(cookie["domain"]):
            continue
        if not cookie["name"] or len(cookie["value"]) > 65536 or not isinstance(cookie.get("path", "/"), str):
            raise AuthError("invalid_cookies", "浏览器会话格式无效。")
        expires = cookie.get("expires", -1)
        if not isinstance(expires, (int, float)):
            raise AuthError("invalid_cookies", "浏览器会话有效期格式无效。")
        filtered.append({key: cookie[key] for key in ("name", "value", "domain", "path", "expires", "secure", "httpOnly", "sameSite") if key in cookie})
    cookies = filtered
    if not any(c.get("name") == "JSESSIONID" and c.get("domain", "").lstrip(".") == "course.pku.edu.cn" for c in cookies):
        raise AuthError("login_required", "官方浏览器尚未返回教学网会话，请先完成登录。")
    with _lock:
        try:
            state = load_state()
        except AuthError as exc:
            if exc.code not in ("login_required", "session_unreadable"):
                raise
            state = {"cookies": [], "origins": []}
        merged = {(c["domain"], c.get("path", "/"), c["name"]): c for c in state.get("cookies", [])}
        merged.update({(c["domain"], c.get("path", "/"), c["name"]): c for c in cookies})
        candidate = {**state, "cookies": list(merged.values())}
        # A login-page JSESSIONID alone is not authentication. Only a successful
        # official SSO may replace the last encrypted state, including after moving PCs.
        _acquire_token(candidate, force=True)
    return auth_status(ensure=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Manage PKU Classroom's encrypted official login session")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    try:
        if args.refresh:
            acquire_token(force=True)
        print(json.dumps(auth_status(), ensure_ascii=True))
    except AuthError as exc:
        print(json.dumps({"token": False, "code": exc.code, "message": str(exc)}, ensure_ascii=True))
        raise SystemExit(1)
