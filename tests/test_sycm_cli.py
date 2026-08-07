import sys
from argparse import Namespace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sycm_cli


def test_profile_roundtrip_and_list(monkeypatch, tmp_path):
    monkeypatch.setattr(sycm_cli, "PROFILE_DIR", tmp_path)
    cookies = {"_tb_token_": "tok", "cookie2": "durable", "unb": "1"}
    path = sycm_cli.save_taobao_profile("示例主店", cookies)
    assert path.exists()
    assert (path.stat().st_mode & 0o777) == 0o600
    assert sycm_cli.load_taobao_profile("示例主店") == cookies
    assert "示例主店" in [p["store"] for p in sycm_cli.list_taobao_profiles()]


def test_profile_missing_bad_name_and_no_token(monkeypatch, tmp_path):
    monkeypatch.setattr(sycm_cli, "PROFILE_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="不存在"):
        sycm_cli.load_taobao_profile("没有的店")
    for bad in ("../x", "a/b", ".hidden"):
        with pytest.raises(ValueError, match="简单名字"):
            sycm_cli._profile_path(bad)
    sycm_cli.save_taobao_profile("残缺店", {"cookie2": "x"})
    with pytest.raises(RuntimeError, match="_tb_token_"):
        sycm_cli.load_taobao_profile("残缺店")


class Response:
    status_code = 200
    text = '{"success":true,"code":200,"data":{}}'

    def json(self):
        return {"success": True, "code": 200, "data": {}}


def test_business_error_raises():
    with pytest.raises(RuntimeError, match="业务失败"):
        sycm_cli._validate_business_response({
            "success": False, "code": 401, "message": "请登录"
        })


def test_cc_v2_code_zero_passes():
    sycm_cli._validate_business_response({"code": 0, "data": []})


def test_transient_network_error_is_retried(monkeypatch):
    calls = []

    def get(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise sycm_cli.requests.exceptions.Timeout("timeout")
        return Response()

    monkeypatch.setattr(sycm_cli.requests, "get", get)
    monkeypatch.setattr(sycm_cli.time, "sleep", lambda _: None)
    monkeypatch.setattr(sycm_cli, "MAX_RETRIES", 2)
    payload = sycm_cli._api_get("test", {}, {}, referer="https://example.test")
    assert payload["success"] is True
    assert len(calls) == 2


def test_flatten_menu_extracts_nested_nodes_once():
    payload = {"data": [{
        "menuId": 1, "parentId": 0, "menuName": "交易", "menuPath": "/trade",
        "isVisible": "y", "children": [{
            "menuId": 2, "parentId": 1, "menuName": "销售", "menuPath": "/sale",
            "isVisible": "y",
        }],
    }]}
    rows = sycm_cli._flatten_menu(payload)
    assert {r["menuId"] for r in rows} == {1, 2}
    assert next(r for r in rows if r["menuId"] == 2)["menuPath"] == "/sale"


def test_home_board_commands_hit_verified_paths(monkeypatch):
    seen = []

    def fake_api_get(path, params, cookies, referer=None):
        seen.append((path, params, referer))
        return {"hasError": False,
                "content": {"code": 0, "data": {"self": {"payAmt": {"value": 1}}}}}

    monkeypatch.setattr(sycm_cli, "_api_get", fake_api_get)
    monkeypatch.setattr(sycm_cli, "load_taobao_cookies", lambda: {"_tb_token_": "t"})

    base = dict(date="2026-07-17", raw=False, out=None)
    sycm_cli.cmd_home_overview(Namespace(**base))
    sycm_cli.cmd_home_trend(Namespace(**base))
    sycm_cli.cmd_grow_factor(Namespace(**base))

    paths = {s[0] for s in seen}
    assert paths == {
        "/portal/coreIndex/new/overview/v3.json",
        "/portal/coreIndex/new/trend/v3.json",
        "/portal/board/grow/factor/overview.json",
    }
    by_path = {s[0]: s[1] for s in seen}
    # 数据概览(日 overview) 必须带 needCycleCrc + dateType=day + dateRange
    ov = by_path["/portal/coreIndex/new/overview/v3.json"]
    assert ov["needCycleCrc"] == "true"
    assert ov["dateType"] == "day"
    assert ov["dateRange"] == "2026-07-17|2026-07-17"
    # 增长因子 overview 必须带 device=2
    assert by_path["/portal/board/grow/factor/overview.json"]["device"] == "2"
    # trend 不带 needCycleCrc
    assert "needCycleCrc" not in by_path["/portal/coreIndex/new/trend/v3.json"]
    # 全部走首页 referer
    assert all(r == "https://sycm.taobao.com/portal/home.htm" for _, _, r in seen)


def test_live_guide_uses_har_verified_parameters(monkeypatch):
    seen = {}

    def fake_get(path, params, cookies, referer=None):
        seen.update(path=path, params=params, cookies=cookies, referer=referer)
        return {"code": 0, "data": {}}

    monkeypatch.setattr(sycm_cli, "_api_get", fake_get)
    sycm_cli._fetch_live_guide(
        "/flow/new/live/guide/trend.json",
        start_date="2026-07-12", end_date="2026-07-12", device="0",
        index_code="uv,itmUv,payByrCnt", trend_type="1", cookies={"_tb_token_": "t"},
    )
    assert seen["path"] == "/flow/new/live/guide/trend.json"
    assert seen["params"]["dateRange"] == "2026-07-12|2026-07-12"
    assert seen["params"]["device"] == "0"
    assert seen["params"]["indexCode"] == "uv,itmUv,payByrCnt"
    assert seen["params"]["type"] == "1"
    assert seen["referer"] == "https://sycm.taobao.com/flow/live.htm"


def test_preheating_content_error_exits(monkeypatch):
    monkeypatch.setattr(sycm_cli, "load_taobao_cookies", lambda: {"_tb_token_": "t"})
    monkeypatch.setattr(
        sycm_cli, "_api_get",
        lambda *args, **kwargs: {"hasError": False, "content": {"code": 403, "message": "denied"}},
    )
    with pytest.raises(RuntimeError, match="业务失败 code=403"):
        sycm_cli.cmd_preheating_metrics(Namespace(raw=False, out=None))


def test_order_portal_uses_page_verified_date_contract(monkeypatch):
    seen = {}

    def fake_get(path, params, cookies, referer=None):
        seen.update(path=path, params=params, cookies=cookies, referer=referer)
        return {"hasError": False, "content": {"code": 0, "data": {}}}

    monkeypatch.setattr(sycm_cli, "_api_get", fake_get)
    sycm_cli._fetch_order_portal(
        "/portal/order/distribute.json", date_value="2026-07-11",
        extra={"indexCode": "payOrderByrCnt"}, cookies={"_tb_token_": "t"},
    )
    assert seen["params"]["dateType"] == "day"
    assert seen["params"]["dateRange"] == "2026-07-11|2026-07-11"
    assert seen["params"]["indexCode"] == "payOrderByrCnt"
    assert seen["referer"] == "https://sycm.taobao.com/portal/home.htm"


def test_content_wrapper_rejects_business_error():
    with pytest.raises(RuntimeError, match="业务失败 code=500"):
        sycm_cli._content_data_or_error({
            "hasError": True, "content": {"code": 500, "message": "failed"},
        })


def test_home_table_dates_inclusive_range():
    assert sycm_cli._home_table_dates("2026-07-12", "2026-07-17") == [
        "2026-07-12", "2026-07-13", "2026-07-14",
        "2026-07-15", "2026-07-16", "2026-07-17",
    ]
    # 传反了也自愈
    assert sycm_cli._home_table_dates("2026-07-17", "2026-07-15") == [
        "2026-07-15", "2026-07-16", "2026-07-17",
    ]


def test_fetch_home_table_loops_each_day_with_cyclecrc(monkeypatch):
    seen = []

    def fake_api_get(path, params, cookies, referer=None):
        seen.append((path, params["dateRange"], params.get("needCycleCrc")))
        day = params["dateRange"].split("|")[0]
        return {"hasError": False,
                "content": {"code": 0, "data": {"self": {
                    "payAmt": {"value": 100.0, "cycleCrc": 0.2},
                    "uv": {"value": 5}, "tag": day}}}}

    monkeypatch.setattr(sycm_cli, "_api_get", fake_api_get)
    table = sycm_cli.fetch_home_table(
        "2026-07-16", "2026-07-17", cookies={"_tb_token_": "t"})

    assert set(table) == {"2026-07-16", "2026-07-17"}
    assert table["2026-07-17"]["payAmt"]["value"] == 100.0
    # 每天各一次，且都带 needCycleCrc（较上一周期）
    assert len(seen) == 2
    assert all(nc == "true" for _p, _r, nc in seen)
    assert {r for _p, r, _nc in seen} == {
        "2026-07-16|2026-07-16", "2026-07-17|2026-07-17"}


def test_home_cell_renders_value_and_cyclecrc():
    obj = {"value": 12345.67, "cycleCrc": 0.125}
    assert sycm_cli._home_cell(obj, "amt", show_crc=True) == "12,345.67 +12.5%"
    assert sycm_cli._home_cell(obj, "amt", show_crc=False) == "12,345.67"
    # 百分比字段
    assert sycm_cli._home_cell({"value": 0.1234}, "pct", show_crc=False) == "12.34%"
    # 缺字段（服务端未返回）显示 -
    assert sycm_cli._home_cell(None, "amt", show_crc=True) == "-"


def test_refund_case_end_uses_end_date_fields(monkeypatch):
    seen = {}

    def fake_get(path, params, cookies, referer=None):
        seen.update(path=path, params=params, referer=referer)
        return {"data": {"count": 0, "dataSource": []}}

    monkeypatch.setattr(sycm_cli, "_api_get", fake_get)
    sycm_cli.fetch_refund_all_list(
        start_date="2026-07-17", end_date="2026-07-17",
        query_type="caseEnd", cookies={"_tb_token_": "t"},
    )
    assert seen["path"] == "refund/all/detail/list"
    assert seen["params"]["endStartDate"] == "20260717"
    assert seen["params"]["endEndDate"] == "20260717"
    assert "startDate" not in seen["params"]
    assert seen["params"]["dateRange"] == "1d"


def test_refund_origin_summary_separates_returns_from_unshipped():
    rows = [
        {"caseId": "1", "orderId": "o1", "ordPayTime": "2026-07-17 10:00:00",
         "caseEndTime": "2026-07-17 12:00:00", "caseSceneType": "未发货退款",
         "refundRealAmt": 100},
        {"caseId": "2", "orderId": "o2", "ordPayTime": "2026-07-10 10:00:00",
         "caseEndTime": "2026-07-17 12:00:00", "caseSceneType": "退货退款",
         "refundRealAmt": 200},
    ]
    summary = sycm_cli.summarize_refund_origins(rows)
    assert summary["records"] == 2
    assert summary["refundRealAmt"] == 300
    assert {x["name"]: x["count"] for x in summary["scenes"]} == {
        "未发货退款": 1, "退货退款": 1,
    }
    assert {x["name"]: x["count"] for x in summary["ageBuckets"]}["4-7天"] == 1


def test_fetch_all_refunds_paginates_and_preserves_rows_without_case_id(monkeypatch):
    pages = {
        1: {"data": {"count": 4, "dataSource": [
            {"caseId": "1", "orderId": "o1"},
            {"orderId": "missing-1"},
        ]}},
        2: {"data": {"count": 4, "dataSource": [
            {"caseId": "1", "orderId": "duplicate"},
            {"orderId": "missing-2"},
        ]}},
    }

    def fake_fetch(**kwargs):
        return pages[kwargs["page_no"]]

    monkeypatch.setattr(sycm_cli, "fetch_refund_all_list", fake_fetch)
    rows = sycm_cli.fetch_all_refunds(
        start_date="2026-07-17", end_date="2026-07-17", cookies={"t": "x"},
    )
    assert [row["orderId"] for row in rows] == ["o1", "missing-1", "missing-2"]


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "http://example.com/file.xlsx",
    "https://user:pass@example.com/file.xlsx",
])
def test_download_url_rejects_unsafe_schemes_and_credentials(url):
    with pytest.raises(RuntimeError, match="不安全"):
        sycm_cli._validated_https_url(url)


def test_download_url_accepts_https():
    assert sycm_cli._validated_https_url("https://example.com/file.xlsx") == (
        "https://example.com/file.xlsx"
    )


def test_read_json_rejects_nonlocal_url():
    with pytest.raises(ValueError, match="本机"):
        sycm_cli._read_json("https://example.com/json")


def test_chrome_cookie_file_uses_env_profile(monkeypatch):
    monkeypatch.setenv("SYCM_CHROME_PROFILE", "Profile 1")
    path = sycm_cli._chrome_cookie_file()
    assert path is not None
    assert "Profile 1/Cookies" in path


def test_chrome_cookie_file_none_when_unset(monkeypatch):
    monkeypatch.delenv("SYCM_CHROME_PROFILE", raising=False)
    assert sycm_cli._chrome_cookie_file() is None


def test_read_chrome_taobao_cookies_passes_profile_cookie_file(monkeypatch):
    monkeypatch.setattr(sycm_cli.platform, "system", lambda: "Darwin")
    monkeypatch.setenv("SYCM_CHROME_PROFILE", "Profile 1")
    seen = {}

    def fake_chrome(domain_name=None, cookie_file=None):
        seen["domain_name"] = domain_name
        seen["cookie_file"] = cookie_file
        return []

    monkeypatch.setattr(sycm_cli.browser_cookie3, "chrome", fake_chrome)
    result = sycm_cli._read_chrome_taobao_cookies()
    assert result == {}
    assert seen["cookie_file"] is not None
    assert "Profile 1/Cookies" in seen["cookie_file"]


def test_read_chrome_taobao_cookies_no_cookie_file_when_unset(monkeypatch):
    monkeypatch.setattr(sycm_cli.platform, "system", lambda: "Darwin")
    monkeypatch.delenv("SYCM_CHROME_PROFILE", raising=False)
    seen = {}

    def fake_chrome(domain_name=None, cookie_file=None):
        seen["cookie_file"] = cookie_file
        return []

    monkeypatch.setattr(sycm_cli.browser_cookie3, "chrome", fake_chrome)
    sycm_cli._read_chrome_taobao_cookies()
    assert seen["cookie_file"] is None


# ---------- item-list（商品排行，改指向 /cc/item/view/top.json）----------

# 实测形状（2026-08-05，/cc/item/view/top.json，recent7，真实商品，itemId 已
# 脱敏为占位 123456789）：data 是分页信封 {recordCount, data}；行列表在
# data.data。indexCode 传多少个都不改变返回字段——这里只截取 show 用到的列
# 加一个未用到的字段（subPayOrdAmt）验证多余字段不会破坏渲染。
ITEM_LIST_RESPONSE = {
    "code": 0,
    "data": {
        "recordCount": 2886,
        "data": [
            {
                "item": {"itemId": "123456789", "title": "占位商品甲长标题超过二十四个字用于验证截断效果",
                          "online": True},
                "itemId": {"value": "123456789"},
                "payAmt": {"value": 10551.87, "cycleCrc": -0.0188, "syncCrc": 0.1028},
                "itmUv": {"value": 10184, "cycleCrc": -0.04, "syncCrc": 0.0141},
                "payByrCnt": {"value": 62, "cycleCrc": -0.0159, "syncCrc": 0.2157},
                "payItmCnt": {"value": 66, "cycleCrc": -0.0149, "syncCrc": 0.1186},
                "payRate": {"value": 0.0061, "cycleCrc": 0.0339, "syncCrc": 0.1961},
                "payPct": {"value": 170.1915, "cycleCrc": -0.003, "syncCrc": -0.0929},
                "itemCartCnt": {"value": 362, "cycleCrc": -0.0372, "syncCrc": -0.0646},
                "itemCltByrCnt": {"value": 101, "cycleCrc": -0.038, "syncCrc": 0.4225},
                "stayTimeAvg": {"value": 10.398982038765933, "cycleCrc": 0.0142, "syncCrc": 0.2026},
                "itmBounceRate": {"value": 0.7675, "cycleCrc": -0.0035, "syncCrc": -0.0053},
                "seGuideUv": {"value": 101, "cycleCrc": -0.0194, "syncCrc": 0.0521},
                "sucRefundAmt": {"value": 6466.54, "cycleCrc": 0.0510, "syncCrc": -0.1746},
                "subPayOrdAmt": {"value": 10551.87, "cycleCrc": -0.0188, "syncCrc": 0.1028},
            },
            {
                "item": {"itemId": "987654321", "title": "占位商品乙", "online": True},
                "itemId": {"value": "987654321"},
                "payAmt": {"value": 8401.0},
                "itmUv": {"value": 242},
                "payByrCnt": {"value": 40},
                "payItmCnt": {"value": 57},
                "payRate": {"value": 0.05},
                "payPct": {"value": 210.03},
                "itemCartCnt": {"value": 120},
                "itemCltByrCnt": {"value": 44},
                "stayTimeAvg": {"value": 8.2},
                "itmBounceRate": {"value": 0.6},
                "seGuideUv": {"value": 30},
                "sucRefundAmt": {"value": 100.0},
            },
        ],
    },
}


def test_item_list_preset_hits_view_top_endpoint(monkeypatch):
    seen = {}

    def fake(path, params, cookies, referer=None):
        seen.update(path=path, params=params, referer=referer)
        return ITEM_LIST_RESPONSE

    monkeypatch.setattr(sycm_cli, "_api_get", fake)
    sycm_cli.fetch_preset("item-list", start_date="2026-07-29", end_date="2026-08-04",
                          page_no=1, page_size=5, cookies={"_tb_token_": "tok"})
    assert seen["path"] == "/cc/item/view/top.json"
    assert seen["params"]["dateType"] == "recent7"
    assert seen["params"]["dateRange"] == "2026-07-29|2026-08-04"
    assert seen["params"]["device"] == "0"
    assert seen["params"]["compareType"] == "cycle"
    assert "itmUv" in seen["params"]["indexCode"]
    assert "item_rank" in seen["referer"]


def test_item_list_no_longer_uses_old_portal_endpoint():
    """回归：确保没有静默改回旧接口——旧接口不认 indexCode，只回 3 个指标。"""
    assert sycm_cli.LIST_PRESETS["item-list"]["path"] == "/cc/item/view/top.json"
    assert "/cc/item/portal/itemList.json" not in sycm_cli.LIST_PRESETS["item-list"]["path"]


def test_item_list_renders_more_than_three_metrics(monkeypatch, capsys):
    monkeypatch.setattr(sycm_cli, "_api_get", lambda *a, **k: ITEM_LIST_RESPONSE)
    monkeypatch.setattr(sycm_cli, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    args = Namespace(preset_name="item-list", date="2026-07-29", end_date="2026-08-04",
                     page=1, limit=5, raw=False, out=None)
    sycm_cli.cmd_preset_list(args)
    out = capsys.readouterr().out
    # 表头列数就是 show 里配的列数，必须明显多于旧接口的 3 个
    show = sycm_cli.LIST_PRESETS["item-list"]["show"]
    assert len(show) > 3
    for col in ("payAmt", "itmUv", "payByrCnt", "payItmCnt", "payRate", "payPct",
                "itemCartCnt", "itemCltByrCnt", "stayTimeAvg", "itmBounceRate",
                "seGuideUv", "sucRefundAmt"):
        assert col in show
    # 分页信封的 recordCount 要露出来（旧接口没有这个字段，之前 total_path 是空的）
    assert "2886" in out
    # 嵌套 {value,...} 已解包成标量，不是打印整个 dict
    assert "10551.87" in out
    assert "123456789" in out


def test_item_list_list_path_is_data_data_not_data():
    """response 的分页信封是 {recordCount, data}，行列表在 data.data；
    旧接口(itemList.json)才是 data 本身直接是行列表，别用旧层级。"""
    preset = sycm_cli.LIST_PRESETS["item-list"]
    assert preset["list_path"] == "data.data"
    assert preset["total_path"] == "data.recordCount"


# ---------- 字段字典 (Task 5) ----------

def test_fields_dict_status_is_always_one_of_three():
    """字典是「越用越厚」的，钉死条目总数只会让每次加字段都要改测试数字
    （已经改过一轮）。真正要守的是：规模不缩水 + 每条都有合法 status。"""
    d = sycm_cli.load_fields_dict()
    assert set(v.get("status") for v in d.values()) <= {"verified", "candidate", "rejected"}
    verified = [v for v in d.values() if v.get("status") == "verified"]
    candidate = [v for v in d.values() if v.get("status") == "candidate"]
    assert len(verified) >= 35
    assert len(candidate) >= 35


def test_fields_dict_missing_file_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(sycm_cli, "FIELDS_PATH", tmp_path / "no.json")
    assert sycm_cli.load_fields_dict() == {}


def test_fields_dict_refund_notes_carry_the_gotcha():
    d = sycm_cli.load_fields_dict()
    assert "近7天" in d["ordRfdRate"]["note"]
    assert "近7天" in d["payAmtRfdRate"]["note"]
    assert "近7天" in d["payShopRfdAmt"]["note"]
    assert "T-3" in d["realPayrealRfdRate"]["note"]


def _fake_home_table(monkeypatch):
    fake_table = {
        "2026-07-17": {
            "payAmt": {"value": 12345.678, "cycleCrc": 0.05},
            "uv": {"value": 999},
        },
    }
    monkeypatch.setattr(
        sycm_cli, "fetch_home_table", lambda *a, **k: fake_table)


def test_home_table_fields_flag_renders_only_selected_field(monkeypatch, capsys):
    _fake_home_table(monkeypatch)
    args = sycm_cli.build_parser().parse_args(
        ["home-table", "--fields", "payAmt"])
    sycm_cli.cmd_home_table(args)
    out = capsys.readouterr().out
    assert "支付金额" in out
    assert "访客数" not in out
    assert "【" not in out  # --fields 模式不分组


def test_home_table_all_fields_flag_renders_verified_and_candidate_groups(
        monkeypatch, capsys):
    _fake_home_table(monkeypatch)
    args = sycm_cli.build_parser().parse_args(
        ["home-table", "--all-fields"])
    sycm_cli.cmd_home_table(args)
    out = capsys.readouterr().out
    assert "支付金额" in out
    assert "【未破译】" in out


def test_home_table_fields_and_all_fields_are_mutually_exclusive():
    parser = sycm_cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["home-table", "--fields", "payAmt", "--all-fields"])


def test_home_table_default_behavior_unchanged(monkeypatch, capsys):
    _fake_home_table(monkeypatch)
    args = sycm_cli.build_parser().parse_args(["home-table"])
    sycm_cli.cmd_home_table(args)
    out = capsys.readouterr().out
    assert "【支付】" in out
    assert "支付金额" in out


def test_new_product_list_requests_all_eight_picker_metrics():
    """页面指标选择器 8 项，早期只传了 6 项（缺收藏人数/加购转化率/支付转化率）。
    2026-08-06 实测一次全传服务端全回，没有静默丢弃，所以不该再少要。"""
    preset = sycm_cli.LIST_PRESETS["new-product-list"]
    codes = set(preset["indexCode"].split(","))
    for metric in ("shopUvNew", "addCartCntNew", "collectCntNew", "addCartRateNew",
                   "payByrCntNew", "payAmtNew", "shopPayRateNew", "uvWorth"):
        assert metric in codes, f"指标选择器里的 {metric} 没传"


# ── 新品趋势渲染（2026-08-07 补）─────────────────────────────────────────
# 原来只打「self: 1 项 / industry: 1 项」+「建议加 --raw 看完整 JSON」，
# 等于没渲染。实际结构很规整：每个指标一条等长序列，statDate 是日期序列。

NPT_DATA = {
    "self": {
        "statDate": [1783440000000, 1783526400000],
        "shopUvNew": [15572, 14990],
        "addCartCntNew": [748, 662],
        "collectCntNew": [147, 141],
        "payByrCntNew": [122, 104],
        "payAmtNew": [19708.47, 16197.69],
        "shopPayRateNew": [0.0078, 0.0069],
        "uvWorth": [1.27, 1.08],
    },
    "industry": {"shopUvNew": [6000, 6600], "shopPayRateNew": [0.0095, 0.0095]},
}


def test_new_product_trend_renders_dates_not_epoch_millis(capsys):
    """statDate 是毫秒时间戳，打 1783440000000 等于没打。"""
    sycm_cli._print_new_product_trend(NPT_DATA)
    out = capsys.readouterr().out
    assert "2026-" in out
    assert "1783440000000" not in out


def test_new_product_trend_renders_one_row_per_day(capsys):
    sycm_cli._print_new_product_trend(NPT_DATA)
    rows = [l for l in capsys.readouterr().out.splitlines() if l.startswith("2026-")]
    assert len(rows) == 2
    assert "15572" in rows[0] and "19708.47" in rows[0]


def test_new_product_trend_rates_are_percent_not_raw_decimal(capsys):
    """0.0078 打成 0.78%，别让人自己乘 100。"""
    sycm_cli._print_new_product_trend(NPT_DATA)
    out = capsys.readouterr().out
    assert "0.78%" in out
    assert "0.0078" not in out


def test_new_product_trend_empty_is_stated_not_silent(capsys):
    sycm_cli._print_new_product_trend({})
    assert "无数据" in capsys.readouterr().out


# ── 展示层统一（2026-08-07）：列名查 fields.json，值按 fmt 打 ─────────────

def test_field_label_uses_dictionary_and_never_invents_chinese():
    assert sycm_cli._field_label("payAmt") == "支付金额"
    # 字典里没有的原样打字段码 —— 不猜中文名
    assert sycm_cli._field_label("zzzNotInDict") == "zzzNotInDict"


def test_field_value_renders_rates_as_percent_not_raw_decimal():
    """0.006838394217482196 没人读得出来那是 0.68%。"""
    assert sycm_cli._field_value("payRate", 0.006838394217482196) == "0.68%"


def test_field_value_falls_back_to_rate_suffix_for_undictionaried_fields():
    """字典没收录的比率不能比改造前还糟。

    itmVstPayByrRate 未入典，改造前靠 Rate 后缀打成 100.00%。
    只查字典的话会退成 1.00 —— 属于回归。
    """
    assert sycm_cli._field_value("itmVstPayByrRate", 1.0) == "100.00%"


def test_field_value_keeps_integer_metrics_integral():
    """服务端给 64.0，字典说是 int，就别打成 64.00。"""
    assert sycm_cli._field_value("payItmCnt", 64.0) == "64"


def test_field_value_renders_epoch_millis_as_date():
    assert sycm_cli._field_value("statDate", 1785945600000).startswith("2026-")
