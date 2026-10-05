"""生意参谋（sycm.taobao.com）的业务检查：接口都是 GET，成功标志是 success / code。"""
from ...core.errors import ApiFailed


def check_payload(client, payload, resp, label: str) -> None:
    if not isinstance(payload, dict):
        raise ApiFailed("响应格式不认识。", endpoint=label, stage="平台返回")
    if payload.get("success") is False:
        raise ApiFailed(f"生意参谋业务失败 code={payload.get('code')}: "
                        f"{payload.get('message') or payload.get('msg') or ''}", endpoint=label, stage="平台返回")
    code = payload.get("code")
    if code not in (None, 0, 200, "0", "200"):
        raise ApiFailed(f"生意参谋业务失败 code={code}: {payload.get('message') or payload.get('msg') or ''}",
                        endpoint=label, stage="平台返回")
