"""MTOP H5 网关（淘宝系通用）：签名、令牌换发、业务失败检查。千牛、1688 等平台共用，只有网关域名不同。

公开算法（H5 web 通用）：
    sign = md5(token + "&" + timestamp + "&" + appKey + "&" + data_json)
    token       = _m_h5_tk cookie 用 "_" 切分取第 0 段
    timestamp   = 当前毫秒时间戳字符串
    appKey      = 12574478（H5 web 公开 appkey，固定值）
    data_json   = JSON.stringify(参数对象, separators=(',',':'))

请求：GET <网关>/{api}/{version}/?jsv=2.6.1&appKey=…&t=…&sign=…&api=…&v=…&type=originaljson&dataType=json&data=<urlencode(data_json)>
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any
from urllib.parse import urlencode

from .errors import ApiFailed, LoginExpired, RetryRequest

H5_APP_KEY = "12574478"
TAOBAO_GATEWAY = "https://h5api.m.taobao.com/h5"
TOKEN_COOKIES = ("_m_h5_tk", "_m_h5_tk_enc")


def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def token_of(h5_tk: str | None) -> str:
    """_m_h5_tk 形如 "abcdef...1234_1700000000000"，下划线前是 token。"""
    if not h5_tk:
        raise ValueError("没有 _m_h5_tk")
    return h5_tk.split("_", 1)[0]


def build_mtop_request(api: str, version: str, data: dict[str, Any] | None, token: str, *,
                       gateway: str = TAOBAO_GATEWAY, timestamp_ms: int | None = None) -> str:
    """构造 MTOP H5 网关请求 URL（签名已包含在查询串里）。timestamp_ms 可注入固定时间戳（测试用）。"""
    ts = str(timestamp_ms if timestamp_ms is not None else int(time.time() * 1000))
    # JSON.stringify 等价：紧凑 + 保留 unicode（不转义中文）
    data_json = json.dumps(data if data is not None else {}, separators=(",", ":"), ensure_ascii=False)
    query = {
        "jsv": "2.6.1", "appKey": H5_APP_KEY, "t": ts, "sign": _md5(f"{token}&{ts}&{H5_APP_KEY}&{data_json}"),
        "api": api, "v": version, "type": "originaljson", "dataType": "json", "data": data_json,
    }
    return f"{gateway}/{api}/{version}/?{urlencode(query)}"


def is_sign_error(mtop_resp: dict[str, Any]) -> bool:
    """MTOP 响应是不是 sign / 令牌 / 鉴权类错误。这类错误服务端通常会在响应里下发新的 _m_h5_tk，调用方可换发后重签重试。
    覆盖 EMPTY / EXPIRED / ILLEGAL 等各种令牌失效写法（含官方拼写错误 EXOIRED）。"""
    ret = mtop_resp.get("ret", [])
    if isinstance(ret, list):
        for r in ret:
            if not isinstance(r, str):
                continue
            up = r.upper()
            if "FAIL_SYS" in up and "TOKEN" in up:
                return True
            if "FAIL_SYS_ILEGAL_ACCESS" in up or "FAIL_SYS_ILLEGAL_ACCESS" in up or "ILLEGAL_REQUEST" in up:
                return True
    return False


def is_session_expired(mtop_resp: dict[str, Any]) -> bool:
    """登录会话本身过期（和令牌过期不同：换发令牌也救不回来，要用户重新登录）。"""
    ret = mtop_resp.get("ret", [])
    return isinstance(ret, list) and any(isinstance(r, str) and "SESSION_EXPIRED" in r.upper() for r in ret)


def refreshed_h5_cookies(resp: Any) -> dict[str, str]:
    """从响应 Set-Cookie 里取服务端换发的 _m_h5_tk / _m_h5_tk_enc。

    这些 cookie 带 Partitioned 属性，curl_cffi 不会解析进 resp.cookies，因此直接读原始 Set-Cookie 头（可能有多条）。
    """
    try:
        items = list(resp.headers.multi_items())
    except Exception:
        raw = getattr(resp, "headers", {}) and resp.headers.get("set-cookie")
        items = [("set-cookie", raw)] if raw else []
    out: dict[str, str] = {}
    for key, value in items:
        if key.lower() != "set-cookie" or not value:
            continue
        # 一条 Set-Cookie 头可能被合并成逗号分隔；按 "name=" 边界找目标 cookie。
        for name in TOKEN_COOKIES:
            marker = f"{name}="
            idx = value.find(marker)
            if idx == -1:
                continue
            out[name] = value[idx + len(marker):].split(";", 1)[0].strip()
    return out


def signed_request(client, gateway: str, path: str, params: dict) -> tuple[str, dict, dict]:
    """Platform.build_request 的通用实现：路径写成 /<api>/<version>/，参数是业务 data，由这里签名。"""
    api, _, version = path.strip("/").partition("/")
    # 还没有令牌（这个浏览器从没调过 MTOP）：用空令牌发一次，网关会回「令牌为空」并下发新令牌，check_mtop 再重签重发。
    tk = client.cookie("_m_h5_tk")
    url = build_mtop_request(api, version.strip("/") or "1.0", params, token_of(tk) if tk else "", gateway=gateway)
    return url, {}, {}


def _business_failure(payload: dict[str, Any], label: str) -> None:
    """把 MTOP / 内层业务失败转换为命令失败。"""
    ret = payload.get("ret") or []
    if ret and not any(isinstance(r, str) and "SUCCESS" in r for r in ret):
        raise ApiFailed(f"MTOP 业务失败 ret={ret}", endpoint=label, stage="平台返回")
    data = payload.get("data") or {}
    if isinstance(data, dict) and data.get("errorCode"):
        raise ApiFailed(f"MTOP 业务失败 errorCode={data.get('errorCode')}: {data.get('errorMsg') or ''}",
                        endpoint=label, stage="平台返回")
    result = data.get("result") if isinstance(data, dict) else None
    if isinstance(result, str) and result.startswith("{"):
        try:
            inner = json.loads(result)
        except json.JSONDecodeError:
            return
        if inner.get("success") is False:
            raise ApiFailed(f"MTOP 内层业务失败: {inner.get('msg') or inner}", endpoint=label, stage="平台返回")


def check_mtop(client, payload: dict[str, Any], resp: Any, label: str) -> None:
    """Platform.check_payload 的通用实现：令牌失效 → 换发后让底座重签重发（只一次）；会话过期 → 登录失效；其余业务失败 → 报错。"""
    if is_session_expired(payload):
        raise LoginExpired(f"登录会话已过期 ret={payload.get('ret')}。", endpoint=label, stage="登录检查",
                           hint=client.login_hint)
    if is_sign_error(payload):
        if client.state.get("mtop_retrying"):
            client.state["mtop_retrying"] = False
            raise LoginExpired(f"MTOP 鉴权失败 ret={payload.get('ret')}。通常是登录态过期或 sign 错误。",
                               endpoint=label, stage="登录检查", hint=client.login_hint)
        # 服务端在鉴权失败响应里换发了新 _m_h5_tk：插件模式下浏览器已自己接收，命令行模式从 Set-Cookie 取来，然后重签重发。
        fresh = refreshed_h5_cookies(resp)
        if hasattr(client.session, "cookie") or fresh.get("_m_h5_tk"):
            for k, v in fresh.items():
                client.set_cookie(k, v)
            client.state["mtop_retrying"] = True
            raise RetryRequest()
        raise LoginExpired(f"MTOP 鉴权失败 ret={payload.get('ret')}。通常是登录态过期或 sign 错误。",
                           endpoint=label, stage="登录检查", hint=client.login_hint)
    client.state["mtop_retrying"] = False
    _business_failure(payload, label)
