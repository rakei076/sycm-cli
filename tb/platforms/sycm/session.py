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


# 客服类列表：每一行是本店的一条记录，带 sellerId。客户 10/14 实测这几个接口会在同一登录能看的几家店之间随机跳
# （同一页请求两次落在不同的店），所以按行里的 sellerId 认店。别的列表里的 sellerId 可能是竞店、同行，不能拿来认。
ROW_SHOP_PATHS = ("/csp/api/ww/consultation/detail/list", "/csp/api/inquiry/loss/list",
                  "/csp/api/ww/sale/detail/list", "/csp/api/evaluation/detail/list")


def _plain(v):
    v = v.get("value") if isinstance(v, dict) else v
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return None if v in (None, "", 0) else str(v)


def shop_of(payload, url: str = "") -> str | None:
    """回包是哪家店的（店铺编号）。认不出返回 None。
    - 首页一类接口在 data（或 data.self）里带 userId，值可能包一层 {value: …}；
    - 客服类列表看每一行的 sellerId：几行不是同一家店时返回「多家店：…」，和哪家店都对不上，会被重发、最后拦下。"""
    if not isinstance(payload, dict):
        return None
    content = payload.get("content") if isinstance(payload.get("content"), dict) else payload
    data = content.get("data")
    for box in (data, data.get("self") if isinstance(data, dict) else None):
        if isinstance(box, dict) and "userId" in box:
            shop = _plain(box["userId"])
            if shop:
                return shop
    if url.split("?", 1)[0].endswith(ROW_SHOP_PATHS) and isinstance(data, dict):
        rows = data.get("dataSource") or data.get("data") or data.get("list") or []
        ids = sorted({_plain(r.get("sellerId")) for r in rows if isinstance(r, dict)} - {None})
        if len(ids) == 1:
            return ids[0]
        if ids:
            return "多家店：" + "、".join(ids)
    return None
