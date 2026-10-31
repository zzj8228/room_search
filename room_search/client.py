"""Authenticated catalog client, independent of the replay project."""
import json
import urllib.error
import urllib.parse
import urllib.request

from .auth import AuthError, acquire_token

BASE = "https://onlineroomse.pku.edu.cn/courseapi/v2"


def api_get(path, params, token, retry_auth=True):
    request = urllib.request.Request(BASE + "/" + path + "?" + urllib.parse.urlencode(params),
        headers={"Authorization": "Bearer " + token, "Accept": "application/json",
                 "Referer": "https://onlineroomse.pku.edu.cn/", "User-Agent": "Mozilla/5.0 PKUClassroom/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = json.loads(response.read(16 * 1024 * 1024))
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            if retry_auth:
                return api_get(path, params, acquire_token(force=True), False)
            raise AuthError("session_rejected", "课表软件的独立登录态已过期，请重新登录。") from None
        raise RuntimeError(f"智云目录返回 HTTP {error.code}，旧数据保留。") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError("无法连接智云目录，请检查校园网和代理；旧数据保留。") from None
    except (ValueError, UnicodeError):
        raise RuntimeError("目录没有返回有效 JSON；旧数据保留。") from None
    if not isinstance(data, dict) or data.get("code") != 0:
        raise AuthError("session_rejected", "智云目录未接受请求，请检查课表软件独立登录状态。")
    return data
