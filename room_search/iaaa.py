"""IAAA's PKU App QR flow; tickets and cookies never leave the server."""
import http.cookiejar
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from . import auth

BASE = "https://iaaa.pku.edu.cn/iaaa/"
APP_ID = "blackboard"
# This is the teaching platform's registered redirect value, not our website.
REGISTERED_REDIRECT = "http://course.pku.edu.cn/webapps/bb-sso-BBLEARN/execute/authValidate/campusLogin"
# Never send the temporary ticket over the registered legacy HTTP URL.
HTTPS_CALLBACK = "https://course.pku.edu.cn/webapps/bb-sso-BBLEARN/execute/authValidate/campusLogin"


class QRLogin:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            auth.OfficialRedirects(), urllib.request.HTTPCookieProcessor(self.cookies))
        self.deadline = time.monotonic() + 180

    def request(self, url, form=None, image=False):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise auth.AuthError("qr_expired", "二维码已过期，请重新扫码登录。")
        headers = {"User-Agent": "Mozilla/5.0", "Referer": BASE + "oauth.jsp",
                   "Accept": "image/png,image/jpeg" if image else "application/json,text/html"}
        data = None
        if form is not None:
            data = urllib.parse.urlencode(form).encode("ascii")
            headers.update({"Content-Type": "application/x-www-form-urlencoded",
                            "X-Requested-With": "XMLHttpRequest"})
        request = urllib.request.Request(url, data=data, headers=headers)
        try:
            with self.opener.open(request, timeout=min(15, remaining)) as response:
                body = response.read(1024 * 1024 + 1)
                mime = response.headers.get_content_type()
        except (urllib.error.URLError, OSError, TimeoutError):
            # HTTPError can contain the callback ticket in its URL. Never expose it.
            raise auth.AuthError("network_error", "无法连接 IAAA，请检查服务器校园网及 TLS 证书后重试。") from None
        if len(body) > 1024 * 1024:
            raise auth.AuthError("invalid_response", "IAAA 响应过大，已停止登录。")
        return body, mime

    def begin(self):
        self.request(BASE + "oauth.jsp?" + urllib.parse.urlencode(
            {"appID": APP_ID, "appName": "北京大学教学网", "redirectUrl": REGISTERED_REDIRECT}))
        body, mime = self.request(BASE + "genQRCode.do?" + urllib.parse.urlencode(
            {"userName": "", "_rand": secrets.token_hex(12), "appId": APP_ID}), image=True)
        if body.startswith(b"\x89PNG\r\n\x1a\n") and mime == "image/png":
            return body, mime
        if body.startswith(b"\xff\xd8\xff") and mime == "image/jpeg":
            return body, mime
        raise auth.AuthError("invalid_response", "IAAA 未返回有效二维码，请稍后重试。")

    def poll(self):
        body, _mime = self.request(BASE + "oauthlogin4QRCode.do", {
            "appId": "PKUApp", "issuerAppId": "iaaa", "targetAppId": APP_ID,
            "redirectUrl": REGISTERED_REDIRECT})
        try:
            result = json.loads(body)
        except (ValueError, UnicodeError):
            raise auth.AuthError("invalid_response", "IAAA 扫码响应无效，请重新登录。") from None
        if not isinstance(result, dict):
            raise auth.AuthError("invalid_response", "IAAA 扫码响应无效，请重新登录。")
        if result.get("success") is True:
            ticket = result.get("token")
            if not isinstance(ticket, str) or not ticket or len(ticket) > 16384:
                raise auth.AuthError("invalid_response", "IAAA 未返回有效授权，请重新登录。")
            return ticket
        errors = result.get("errors")
        code = errors.get("code") if isinstance(errors, dict) else None
        if code == "E10" and result.get("isStop") != "是":
            return None
        messages = {"E99": "二维码已失效，请重新扫码登录。", "E02": "账号需要在官方 IAAA 网站激活。",
                    "E06": "IAAA 要求额外验证，请在官方 App 中完成账号验证后重试。"}
        # Do not echo upstream messages or arbitrary response fields.
        raise auth.AuthError("qr_rejected", messages.get(code, "IAAA 未接受扫码授权，请重新登录。"))

    def complete(self, ticket):
        self.request(HTTPS_CALLBACK + "?" + urllib.parse.urlencode(
            {"_rand": secrets.token_hex(12), "token": ticket}))
        # IAAA SSO cookies are broader than needed. Persist only teaching cookies,
        # after the existing client has verified teaching -> Zhiyun authorization.
        state = auth.jar_state(self.cookies, {"cookies": [], "origins": []})
        state["cookies"] = [cookie for cookie in state["cookies"]
                            if cookie["domain"].lstrip(".").lower() == "course.pku.edu.cn"]
        if not any(cookie["name"] == "JSESSIONID" for cookie in state["cookies"]):
            raise auth.AuthError("login_required", "教学网未建立登录会话，请重新扫码。")
        auth._acquire_token(state, force=True)

    def close(self):
        self.cookies.clear()
