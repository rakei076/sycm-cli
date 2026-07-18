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
