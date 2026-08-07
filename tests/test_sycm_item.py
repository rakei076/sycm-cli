import argparse
import json
import sys
from argparse import Namespace
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sycm_cli
import sycm_item


@pytest.fixture(autouse=True)
def sleep_calls(monkeypatch):
    """测试不真的睡 1.8~3.5 秒，同时记下调用次数供节流断言用。"""
    calls: list[str] = []
    monkeypatch.setattr(sycm_item, "_sleep_humanlike", lambda: calls.append("slept"))
    return calls


SEARCH_RESPONSE = {
    "code": 0,
    "data": [
        {"id": 123456789, "itemNO": "A1001", "title": "占位商品甲",
         "price": 199.0, "stockCnt": 12, "pictUrl": "//img/x.jpg",
         "url": "//detail.tmall.com/item.htm?id=123456789"},
        {"id": 987654321, "itemNO": "A1002", "title": "占位商品乙",
         "price": 259.0, "stockCnt": 0, "pictUrl": "//img/y.jpg",
         "url": "//detail.tmall.com/item.htm?id=987654321"},
    ],
}


def test_search_items_normalizes_id_to_string(monkeypatch):
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: SEARCH_RESPONSE)
    rows = sycm_item.search_items("占位", cookies={"_tb_token_": "tok"})
    assert [r["itemId"] for r in rows] == ["123456789", "987654321"]
    assert rows[0]["itemNO"] == "A1001"
    assert rows[0]["stockCnt"] == 12


def test_search_items_empty_data(monkeypatch):
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: {"code": 0, "data": None})
    assert sycm_item.search_items("查无此款", cookies={"_tb_token_": "tok"}) == []


def test_search_passes_keyword_and_referer(monkeypatch):
    seen = {}

    def fake(path, params, cookies, referer=None):
        seen.update(path=path, params=params, referer=referer)
        return SEARCH_RESPONSE

    monkeypatch.setattr(sycm_item, "_api_get", fake)
    sycm_item.search_items("A1001", cookies={"_tb_token_": "tok"})
    assert seen["path"] == "/cc/common/item/search.json"
    assert seen["params"]["keyword"] == "A1001"
    assert seen["params"]["token"] == "tok"
    assert "item_archives" in seen["referer"]


def test_resolve_item_id_prefers_explicit_id():
    args = Namespace(item_id="123456789", search=None)
    assert sycm_item.resolve_item_id(args, cookies={"_tb_token_": "tok"}) == "123456789"


def test_resolve_item_id_unique_search_hit(monkeypatch):
    monkeypatch.setattr(sycm_item, "search_items",
                        lambda kw, cookies=None: [{"itemId": "123456789",
                                                    "itemNO": "A1001",
                                                    "title": "占位商品甲"}])
    args = Namespace(item_id=None, search="A1001")
    assert sycm_item.resolve_item_id(args, cookies={"_tb_token_": "tok"}) == "123456789"


def test_resolve_item_id_multiple_hits_exits(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "search_items",
                        lambda kw, cookies=None: [
                            {"itemId": "123456789", "itemNO": "A1001", "title": "甲"},
                            {"itemId": "987654321", "itemNO": "A1002", "title": "乙"},
                        ])
    args = Namespace(item_id=None, search="占位")
    with pytest.raises(SystemExit) as exc:
        sycm_item.resolve_item_id(args, cookies={"_tb_token_": "tok"})
    assert exc.value.code == 1
    assert "命中 2 个" in capsys.readouterr().err


def test_resolve_item_id_no_hit_exits(monkeypatch):
    monkeypatch.setattr(sycm_item, "search_items", lambda kw, cookies=None: [])
    args = Namespace(item_id=None, search="查无此款")
    with pytest.raises(SystemExit) as exc:
        sycm_item.resolve_item_id(args, cookies={"_tb_token_": "tok"})
    assert exc.value.code == 1


def test_resolve_item_id_requires_one_of_them():
    args = Namespace(item_id=None, search=None)
    with pytest.raises(SystemExit):
        sycm_item.resolve_item_id(args, cookies={"_tb_token_": "tok"})


SKU_RESPONSE = {
    # 实测形状（2026-08-05，/cc/item/sale/sku/list.json，recent30，真实商品）：
    # data 是分页信封 {recordCount, data}；行列表在 data.data。
    # 没有 live 接口那层 {updateTime, interval, data, timestamp} 外层信封，
    # 也没有 currentStockCnt/sellRate/stockDays——这三个库存字段实测在这个
    # 日期口径接口上会被静默丢弃（indexCode 加了也不返回）。
    "code": 0,
    "data": {
        "recordCount": 1,
        "data": [
            {"skuId": {"value": "111"}, "skuName": {"value": "颜色:黑色;尺码:L"},
             "itemId": {"value": "123456789"},
             "cartCnt": {"value": 8}, "payAmt": {"value": 1990.0},
             "payItmCnt": {"value": 10}, "payByrCnt": {"value": 9}},
        ],
    },
}

ATTR_RESPONSE = {
    # 实测形状（2026-08-05，/cc/item/sale/sku/attrDetail.json，attrName=尺码，
    # recent30，真实商品）：跟 sku/list 同款分页信封 {recordCount, data}。
    "code": 0,
    "data": {
        "recordCount": 2,
        "data": [
            {"attrValue": {"value": "XL"}, "cartCnt": {"value": 342.0},
             "payAmt": {"value": 9497.79, "ratio": 0.3018},
             "payAmtRatio": {"value": 0.3018}, "payItmCnt": {"value": 64.0},
             "payByrCnt": {"value": 57.0, "ratio": 0.2879},
             "payByrCntRatio": {"value": 0.2879}},
            {"attrValue": {"value": "L"}, "cartCnt": {"value": 423.0},
             "payAmt": {"value": 5026.99, "ratio": 0.1597},
             "payAmtRatio": {"value": 0.1597}, "payItmCnt": {"value": 33.0},
             "payByrCnt": {"value": 33.0, "ratio": 0.1667},
             "payByrCntRatio": {"value": 0.1667}},
        ],
    },
}


def test_item_sku_list_builds_expected_params(monkeypatch):
    seen = {}

    def fake(path, params, cookies, referer=None):
        seen.update(path=path, params=params)
        return SKU_RESPONSE

    monkeypatch.setattr(sycm_item, "_api_get", fake)
    sycm_item.fetch_item_preset(
        "item-sku-list", item_id="123456789",
        start_date="2026-08-04", end_date="2026-08-04",
        page_no=1, page_size=10, cookies={"_tb_token_": "tok"},
    )
    assert seen["path"] == "/cc/item/sale/sku/list.json"
    assert seen["params"]["itemId"] == "123456789"
    assert seen["params"]["dateType"] == "day"
    assert seen["params"]["device"] == "0"


def test_item_sku_list_flattens_nested_values(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: SKU_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    args = Namespace(item_id="123456789", search=None, date="2026-08-04",
                     end_date=None, limit=10, page=1, raw=False, out=None, by=None)
    sycm_item.cmd_item_sku_list(args)
    out = capsys.readouterr().out
    assert "颜色:黑色;尺码:L" in out
    assert "1990.0" in out
    # 表头用中文名（2026-08-07 起查 fields.json，不再直打字段码）
    assert "加购件数" in out and "cartCnt" not in out


def test_item_sku_list_by_attr_calls_attr_detail_endpoint(monkeypatch, capsys):
    """--by <属性名> 时要打 attrDetail.json，带上 attrName，出的是聚合表不是
    SKU 组合明细。"""
    seen = {}

    def fake(path, params, cookies, referer=None):
        seen.update(path=path, params=params)
        return ATTR_RESPONSE

    monkeypatch.setattr(sycm_item, "_api_get", fake)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    args = Namespace(item_id="123456789", search=None, date="2026-07-06",
                     end_date="2026-08-04", limit=10, page=1, raw=False,
                     out=None, by="尺码")
    sycm_item.cmd_item_sku_list(args)
    assert seen["path"] == "/cc/item/sale/sku/attrDetail.json"
    assert seen["params"]["attrName"] == "尺码"
    out = capsys.readouterr().out
    assert "XL" in out
    assert "9497.79" in out
    # payAmtRatio 是接口自带的比率，不是我们算的；
    # 2026-08-07 起按字典 fmt=pct 打成百分比，裸小数没人读得出来
    assert "30.18%" in out and "0.3018" not in out


# 实测形状（2026-08-05，/cc/live/v2/item/sale/sku/list.json，真实商品，
# itemId 已脱敏为占位 123456789）：比认日期的 /cc/item/sale/sku/list.json
# 多一层信封——data:{updateTime, interval, data:{recordCount, data:[...]},
# timestamp}，行列表在 data.data.data（三层）。currentStockCnt/sellRate/
# stockDays 是裸标量，不像 cartCnt/payAmt 那样包一层 {value,...}。
SKU_LIVE_RESPONSE = {
    "code": 0,
    "data": {
        "updateTime": "2026-08-05 22:46:15",
        "interval": 30,
        "data": {
            "recordCount": 1,
            "data": [
                {"skuName": {"value": "颜色分类:黑色长款;尺码:L"},
                 "itemId": {"value": "123456789"},
                 "cartCnt": {"value": 9}, "payAmt": {"value": 150.24},
                 "payItmCnt": {"value": 1}, "payByrCnt": {"value": 1},
                 "currentStockCnt": 2, "sellRate": 0.3333333333,
                 "stockDays": 2},
            ],
        },
        "timestamp": 1785941175899,
    },
}


def test_item_sku_list_live_hits_realtime_endpoint_and_warns(monkeypatch, capsys):
    """--live 要打实时接口、带上库存类 indexCode，且要在 stderr 明确提示
    --date 不生效——这三个库存字段只有实时接口才有，日期口径接口拿不到。"""
    seen = {}

    def fake(path, params, cookies, referer=None):
        seen.update(path=path, params=params)
        return SKU_LIVE_RESPONSE

    monkeypatch.setattr(sycm_item, "_api_get", fake)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    args = Namespace(item_id="123456789", search=None, date="2026-08-04",
                     end_date=None, limit=10, page=1, raw=False, out=None,
                     by=None, live=True)
    sycm_item.cmd_item_sku_list(args)
    assert seen["path"] == "/cc/live/v2/item/sale/sku/list.json"
    assert "currentStockCnt" in seen["params"]["indexCode"]
    assert "sellRate" in seen["params"]["indexCode"]
    assert "stockDays" in seen["params"]["indexCode"]
    captured = capsys.readouterr()
    assert "--date" in captured.err and "不生效" in captured.err
    assert "颜色分类:黑色长款;尺码:L" in captured.out
    assert "2" in captured.out  # currentStockCnt / stockDays 裸标量也要能渲染


def test_item_sku_list_live_uses_three_level_list_path():
    """回归：实时接口比日期口径接口多一层信封，list_path 必须是三层，
    别照抄两层那个的 data.data（历史上这层数错过一次，本项目最容易踩的坑）。"""
    preset = sycm_item.ITEM_PRESETS["item-sku-list-live"]
    assert preset["list_path"] == "data.data.data"
    assert sycm_item.ITEM_PRESETS["item-sku-list"]["list_path"] == "data.data"


def test_item_sku_list_by_and_live_are_mutually_exclusive():
    """--by 和 --live 不能同时给：--live 是固定字段集的实时快照，没有按属性
    聚合的版本；argparse 的互斥组要在解析阶段就拦下来，不用等到命令里报错。"""
    import sycm_cli
    parser = sycm_cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["item-sku-list", "--item-id", "123456789",
                           "--by", "尺码", "--live"])


def test_print_rows_fails_fast_on_wrong_list_path(monkeypatch, capsys):
    """list_path 配错层级、_dig 拿到 dict 而不是 list 时，要报清楚的错，
    不能是 KeyError: slice(...) 那种没头没脑的 traceback（bug 5）。"""
    # 故意让 preset 的 list_path 指向分页信封本身（data）而不是信封里的行
    # 列表（data.data），模拟配错层级、_dig 拿到 dict 的场景。
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: SKU_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    args = Namespace(item_id="123456789", search=None, date="2026-08-04",
                     end_date=None, limit=10, page=1, raw=False, out=None, by=None)
    broken_preset = dict(sycm_item.ITEM_PRESETS["item-sku-list"])
    broken_preset["list_path"] = "data"  # 配错层级：取到分页信封本身
    monkeypatch.setitem(sycm_item.ITEM_PRESETS, "item-sku-list", broken_preset)
    with pytest.raises(SystemExit) as exc:
        sycm_item.cmd_item_sku_list(args)
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "list_path" in err
    assert "dict" in err  # 报出实际拿到的类型，而不是甩 KeyError


def test_search_items_skips_rows_without_id(monkeypatch):
    """缺 id 的行会产出 itemId=""，而 resolve_item_id 会把空串当有效值返回，
    后续请求就少了 itemId 参数，可能拉回全店数据。这种行必须丢掉。"""
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: {
        "code": 0, "data": [
            {"itemNO": "A1001", "title": "缺 id 的行"},
            {"id": None, "itemNO": "A1002", "title": "id 是 null"},
            {"id": 123456789, "itemNO": "A1003", "title": "正常行"},
        ]})
    rows = sycm_item.search_items("占位", cookies={"_tb_token_": "tok"})
    assert [r["itemId"] for r in rows] == ["123456789"]


def test_resolve_item_id_reports_hidden_candidates(monkeypatch, capsys):
    """搜索最多返回 50 个而候选只列前 20 个，剩下的必须说一声还有多少。"""
    monkeypatch.setattr(sycm_item, "search_items", lambda kw, cookies=None: [
        {"itemId": str(100000000 + i), "itemNO": f"A{i}", "title": f"款{i}"}
        for i in range(50)])
    args = Namespace(item_id=None, search="占位")
    with pytest.raises(SystemExit):
        sycm_item.resolve_item_id(args, cookies={"_tb_token_": "tok"})
    err = capsys.readouterr().err
    assert "还有 30 个未列出" in err


# ---------- 取数与渲染的兜底路径（三个命令都依赖它们） ----------

def test_dig_returns_none_on_missing_key():
    assert sycm_item._dig({"data": {"a": 1}}, "data.nope") is None
    assert sycm_item._dig({}, "data.data.data") is None


def test_dig_returns_none_when_intermediate_node_is_a_list():
    """中间节点是 list 时不能崩，返回 None 让上层走「取不到」分支。"""
    assert sycm_item._dig({"data": [{"x": 1}]}, "data.x") is None


def test_print_rows_renders_missing_column_as_blank(capsys):
    """流量来源的行合法地会缺列，缺列打字面量 "None" 会满屏噪音，要打空白。"""
    preset = {"path": "/x", "list_path": "data", "show": ["a", "b", "c"]}
    sycm_item._print_rows(preset, [{"a": {"value": 1}, "c": "z"}], 10, "表头")
    out = capsys.readouterr().out
    assert "表头" in out
    assert out.strip().splitlines()[-1] == "1\t\tz"
    assert "None" not in out


def test_flatten_source_tree_adds_level_and_path():
    tree = [{
        "pageName": "效果广告",
        "uv": {"value": 100},
        "children": [
            {"pageName": "万相台", "uv": {"value": 60}, "children": []},
            {"pageName": "直通车", "uv": {"value": 40},
             "children": [{"pageName": "关键词推广", "uv": {"value": 25}}]},
        ],
    }]
    flat = sycm_item.flatten_source_tree(tree)
    assert [r["_level"] for r in flat] == [0, 1, 1, 2]
    assert [r["_path"] for r in flat] == [
        "效果广告",
        "效果广告 > 万相台",
        "效果广告 > 直通车",
        "效果广告 > 直通车 > 关键词推广",
    ]
    assert "children" not in flat[0]


def test_flatten_source_tree_handles_empty():
    assert sycm_item.flatten_source_tree([]) == []


FLOW_RESPONSE = {
    "code": 0,
    "data": [{
        "pageName": "效果广告",
        "uv": {"value": 100}, "pv": {"value": 180},
        "cltItmCnt": {"value": 3}, "cartByrCnt": {"value": 9},
        "payByrCnt": {"value": 4}, "payAmt": {"value": 796.0},
        "payRate": {"value": 0.04},
        "children": [
            # 子节点故意缺 payRate：树里父子层级的列并不总是齐的
            {"pageName": "万相台", "uv": {"value": 60}, "pv": {"value": 90},
             "payAmt": {"value": 400.0}},
        ],
    }],
}


def test_item_flow_source_prints_tree_paths(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: FLOW_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    args = Namespace(item_id="123456789", search=None, date="2026-08-04",
                     end_date=None, limit=10, page=1, raw=False, out=None)
    sycm_item.cmd_item_flow_source(args)
    out = capsys.readouterr().out
    assert "效果广告 > 万相台" in out
    assert "796.0" in out
    # 子节点缺的列打空白而不是 "None"
    assert "None" not in out


def test_item_flow_source_raw_and_out(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: FLOW_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    base = dict(item_id="123456789", search=None, date="2026-08-04",
                end_date=None, limit=10, page=1)

    sycm_item.cmd_item_flow_source(Namespace(**base, raw=True, out=None))
    assert json.loads(capsys.readouterr().out) == FLOW_RESPONSE

    target = tmp_path / "flow.json"
    sycm_item.cmd_item_flow_source(Namespace(**base, raw=False, out=str(target)))
    assert json.loads(target.read_text()) == FLOW_RESPONSE
    assert capsys.readouterr().out == ""  # --out 时不往 stdout 打表


REFUND_RESPONSES = {
    # 实测（2026-08-05）：reason/list/v2.json 的 data 本身就是行列表，跟
    # sku/list、prop/list 两个"data.data"分页信封形状不一样。
    "/csp/api/refund/item/reason/list/v2.json": {
        # 实测（2026-08-06，rfdIntervalLevel=99）：中文名在 rfdReasonNameCn，
        # 金额在 itemRfdAmt（itemSucRfdAmt 这个名字不存在、恒 None），
        # rfdReasonTypeCn 分「内部原因 / 消费者原因」。
        "code": 0, "data": [
            {"rfdReasonName": "product", "rfdReasonNameCn": {"value": "商品问题"},
             "rfdReasonTypeCn": {"value": "内部原因"},
             "itemSucRfdByr": {"value": 68}, "itemRfdAmt": {"value": 2388.0},
             "lossByrCnt": {"value": 19}, "payAmtRfdRate": {"value": 0.18}}]},
    "/cc/refund/item/sku/list.json": {
        # 实测真实字段是 itemSkuRfdAmt（不是 itemSkuSucRfdAmt，那个名字不
        # 存在）；payAmtRfdRate / ordRfdRate 是平台自己算好随行返回的退款率，
        # 带着自己的分母 payOrdCnt / payAmt 一起来。
        "code": 0, "data": {"data": [
            {"skuName": "颜色:黑色;尺码:L", "itemSkuSucRfdByr": {"value": 7},
             "itemSkuRfdAmt": {"value": 1393.0},
             "payAmtRfdRate": {"value": 0.18}, "ordRfdRate": {"value": 0.12},
             "payOrdCnt": {"value": 40}, "payAmt": {"value": 7900.0}}]}},
    # 实测（2026-08-05）：propName 是属性名，属性的具体值在 valueName；
    # 行里的值是裸标量，不是 {"value": …} 包裹。
    "/cc/refund/item/prop/list.json": {
        "code": 0, "data": {"data": [
            {"propName": "尺码", "valueName": "2XL", "propId": "20509",
             "itemPropRfdSucByr": 9, "itemPropRfdSucAmt": 1791.0,
             "itemPropOrdRfdRate": 0.74}]}},
}


def test_item_refund_calls_three_endpoints(monkeypatch, capsys):
    called = []

    def fake(path, params, cookies, referer=None):
        called.append(path)
        return REFUND_RESPONSES[path]

    monkeypatch.setattr(sycm_item, "_api_get", fake)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    args = Namespace(item_id="123456789", search=None, date="2026-07-06",
                     end_date="2026-08-04", limit=10, page=1, raw=False, out=None)
    sycm_item.cmd_item_refund(args)
    assert sorted(called) == sorted(REFUND_RESPONSES.keys())
    out = capsys.readouterr().out
    assert "商品问题" in out
    assert "颜色:黑色;尺码:L" in out
    # 属性表必须带上属性值，否则四行全是「尺码」，读者不知道哪个尺码退得多
    assert "2XL" in out
    # 不得自造退款率：数据行里的比率只能来自接口字段。
    # 排除两类非数据行——# 开头的口径说明，以及表头（表头里「金额退款率」
    # 「订单退款率」是 fields.json 里的字段中文名，是列名不是我们算的数）。
    headers = {"\t".join(sycm_item._col_label(c) for c in p["show"])
               for p in sycm_item.ITEM_PRESETS.values() if p.get("show")}
    body = [ln for ln in out.splitlines()
            if ln and not ln.startswith("#") and ln not in headers]
    assert not any("退款率" in ln for ln in body)


def test_item_refund_prints_rate_maturity_warning(monkeypatch, capsys):
    """各 SKU 表展示了平台自算的 payAmtRfdRate/ordRfdRate，而 --date 默认昨天
    正落在「近 7 天仍在爬升」的禁区里，口径说明必须带上成熟度警告。"""
    monkeypatch.setattr(sycm_item, "_api_get",
                        lambda path, *a, **k: REFUND_RESPONSES[path])
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    args = Namespace(item_id="123456789", search=None, date="2026-08-04",
                     end_date=None, limit=10, page=1, raw=False, out=None)
    sycm_item.cmd_item_refund(args)
    out = capsys.readouterr().out
    assert "近 7 天" in out
    assert "payAmtRfdRate" in out


def test_item_refund_reason_empty_prints_explanation_not_bare_table(monkeypatch, capsys):
    """空表要说清「参数已按页面实际请求固定」，让人知道这不是又一次参数猜错。
    2026-08-06 之前这张表恒空，真凶就是 rfdIntervalLevel 猜成了 "ALL"。"""
    responses = dict(REFUND_RESPONSES)
    responses["/csp/api/refund/item/reason/list/v2.json"] = {"code": 0, "data": []}
    monkeypatch.setattr(sycm_item, "_api_get", lambda path, *a, **k: responses[path])
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    args = Namespace(item_id="123456789", search=None, date="2026-07-06",
                     end_date="2026-08-04", limit=10, page=1, raw=False, out=None)
    sycm_item.cmd_item_refund(args)
    out = capsys.readouterr().out
    assert "退款原因  共 0 行" in out
    assert "rfdIntervalLevel=99" in out, "空表说明要写清参数已固定为页面实际值"
    # 兄弟表照常有真实行，证明不是全局取数失败
    assert "颜色:黑色;尺码:L" in out
    assert "2XL" in out


def test_item_refund_throttles_between_requests(monkeypatch, sleep_calls):
    """3 个请求之间必须有 2 次节流；--search 再多一次（搜索请求之后也要隔开）。"""
    monkeypatch.setattr(sycm_item, "_api_get",
                        lambda path, *a, **k: REFUND_RESPONSES[path])
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    args = Namespace(item_id="123456789", search=None, date="2026-07-06",
                     end_date="2026-08-04", limit=10, page=1, raw=False, out=None)
    sycm_item.cmd_item_refund(args)
    assert len(sleep_calls) == 2

    sleep_calls.clear()
    monkeypatch.setattr(sycm_item, "search_items",
                        lambda kw, cookies=None: [{"itemId": "123456789",
                                                    "itemNO": "A1001",
                                                    "title": "占位商品甲"}])
    args = Namespace(item_id=None, search="A1001", date="2026-07-06",
                     end_date="2026-08-04", limit=10, page=1, raw=False, out=None)
    sycm_item.cmd_item_refund(args)
    assert len(sleep_calls) == 3


def test_item_360_throttles_between_requests(monkeypatch, sleep_calls):
    responses = {
        "/cc/diagnose/coreIndex.json": {"code": 0, "data": {"payAmt": {"value": 1.0}}},
        "/cc/item/sale/overview.json": {"code": 0, "data": {"itmUv": {"value": 1}}},
    }
    monkeypatch.setattr(sycm_item, "_api_get", lambda path, *a, **k: responses[path])
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    args = Namespace(item_id="123456789", search=None, date="2026-08-04",
                     end_date=None, limit=10, page=1, raw=False, out=None)
    sycm_item.cmd_item_360(args)
    assert len(sleep_calls) == 1


@pytest.mark.parametrize("name", ["item-refund-reason", "item-refund-sku",
                                   "item-refund-prop"])
def test_refund_presets_all_pin_pay_date_type(name):
    """refundDateType 是口径参数，三个退款接口都要钉死在 pay。"""
    got = sycm_cli.build_query_params(
        sycm_item.ITEM_PRESETS[name],
        start_date="2026-07-06", end_date="2026-08-04",
        page_no=1, page_size=5, token="tok", extra={"itemId": "123456789"},
    )
    assert got["refundDateType"] == "pay"
    assert got["dateType"] == "recent30"


def test_split_compare_fields_groups_quadruplet():
    # 实测形状：coreIndex.json 的 40 个字段全部是 {"value": ...} 包裹，
    # 包括 meta 字段（itemId/statDate 等）；uv 的环比/同行字段用了跟基值不同的
    # 词干（itemUvCrc / itmUvCmpt），payAmt 的同行字段是 payAmtItemCmpt。
    row = {
        "payAmt": {"value": 1000.0}, "payAmtCrc": {"value": 0.12},
        "payAmtItemCmpt": {"value": 800.0}, "payAmtItemCmptCrc": {"value": 0.05},
        "payRate": {"value": 0.03}, "payRateCrc": {"value": -0.01},
        "payRateCmpt": {"value": 0.025}, "payRateCmptCrc": {"value": 0.002},
        "uv": {"value": 1700}, "itemUvCrc": {"value": 0.09},
        "itmUvCmpt": {"value": 0.15}, "itmUvCmptCrc": {"value": 0.02},
        "itemId": {"value": "123456789"}, "statDate": {"value": "2026-08-04"},
    }
    got = sycm_item.split_compare_fields(row)
    # 验证别名表：payAmt 的同行值是 payAmtItemCmpt（非默认的 payAmtCmpt）
    assert got["payAmt"] == {"value": 1000.0, "crc": 0.12,
                             "cmpt": 800.0, "cmptCrc": 0.05}
    assert got["payRate"] == {"value": 0.03, "crc": -0.01,
                              "cmpt": 0.025, "cmptCrc": 0.002}
    # uv 是三词干混用的特例：本店环比叫 itemUvCrc，同行叫 itmUvCmpt
    assert got["uv"] == {"value": 1700, "crc": 0.09,
                         "cmpt": 0.15, "cmptCrc": 0.02}
    # 非指标字段解包后保留在 _meta
    assert got["_meta"]["itemId"] == "123456789"


def test_split_compare_fields_tolerates_missing_compare():
    got = sycm_item.split_compare_fields({"payCnt": {"value": 11}})
    assert got["payCnt"] == {"value": 11, "crc": None, "cmpt": None, "cmptCrc": None}


def test_item_360_prints_core_and_overview(monkeypatch, capsys):
    # 实测形状（2026-08-05，真实商品，recent7 与 recent30 对照）：
    # coreIndex.json 的 data 里全部字段是 {"value": ...} 包裹；
    # /cc/item/sale/overview.json（换掉 live/ 那个后）的 data 本身就是指标
    # 扁平 dict，每个字段是 {value, cycleCrc}，没有信封那层。
    responses = {
        "/cc/diagnose/coreIndex.json": {
            "code": 0, "data": {"payAmt": {"value": 1000.0},
                                 "payAmtCrc": {"value": 0.12},
                                 "payRate": {"value": 0.03},
                                 "payRateCmpt": {"value": 0.025},
                                 "itemId": {"value": "123456789"}}},
        "/cc/item/sale/overview.json": {
            "code": 0, "data": {
                "itmUv": {"value": 1700, "cycleCrc": 0.19},
                "itmPv": {"value": 2807, "cycleCrc": 0.10},
                "payAmt": {"value": 1000.0, "cycleCrc": None},
                "itemId": {"value": "123456789"},
            }},
    }
    monkeypatch.setattr(sycm_item, "_api_get",
                        lambda path, *a, **k: responses[path])
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    args = Namespace(item_id="123456789", search=None, date="2026-08-04",
                     end_date=None, limit=10, page=1, raw=False, out=None)
    sycm_item.cmd_item_360(args)
    out = capsys.readouterr().out
    assert "payRate" in out
    assert "1700" in out


def test_item_360_handles_list_shaped_overview_data(monkeypatch, capsys):
    """overview 的 data 万一返回列表（非当前实测形状，防御性分支）不应崩溃，
    应取第一个元素——list_path 换成 "data" 后这条防御分支仍然要守住。"""
    responses = {
        "/cc/diagnose/coreIndex.json": {
            "code": 0, "data": {"payAmt": {"value": 1000.0},
                                 "itemId": {"value": "123456789"}}},
        "/cc/item/sale/overview.json": {
            "code": 0, "data": [{"itmUv": {"value": 1700}, "itmPv": {"value": 2807}}]},
    }
    monkeypatch.setattr(sycm_item, "_api_get",
                        lambda path, *a, **k: responses[path])
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    args = Namespace(item_id="123456789", search=None, date="2026-08-04",
                     end_date=None, limit=10, page=1, raw=False, out=None)
    sycm_item.cmd_item_360(args)
    out = capsys.readouterr().out
    assert "1700" in out
    assert "2807" in out


def _load_fields():
    path = Path(__file__).resolve().parents[1] / "fields.json"
    return json.loads(path.read_text())


def test_item_domain_fields_present():
    fields = _load_fields()
    item_scoped = {k: v for k, v in fields.items()
                   if any(s.startswith("item-") for s in v.get("scope", []))}
    assert len(item_scoped) >= 12


def _registered_item_commands() -> set[str]:
    """真跑一遍 register()，拿实际挂上去的子命令名。

    原先这里是一串手写的命令名，每加一个不走 preset 的命令就得记得回来补一笔，
    忘了就是一次假失败（item-profile 就撞了这个）。从注册结果里推导，白名单
    自己会跟上。
    """
    import argparse

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    sycm_item.register(sub, "2026-08-04")
    return set(sub.choices)


def _all_cli_commands() -> set[str]:
    """真实主 parser 注册的全部子命令名。别再手工重建一份。"""
    parser = sycm_cli.build_parser()
    names: set[str] = set()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            names |= set(action.choices)
    return names


def test_every_scope_points_to_a_real_command():
    fields = _load_fields()
    # 全部从真实注册表推导：
    #   商品域 → 跑一遍 register() 拿子命令名
    #   主文件 → LIST_PRESETS 的键就是命令名
    # 只有首页大盘那两个不走 preset，仍需显式列出。
    # （硬编码白名单已经害过两次：item-profile 和 new-product-list，
    #   每次都是「加了命令忘了回来补一笔」，所以能推导的一律推导。）
    # 2026-08-07 再改：连「首页大盘那两个显式列出」也去掉了。
    # 直接问真实的主 parser 要全部子命令名 —— 上一版还是半推导半硬编码，
    # 加了 new-product-overview / new-product-trend 又漏了一次。
    known = _all_cli_commands() | set(sycm_item.ITEM_PRESETS)
    for code, meta in fields.items():
        for scope in meta.get("scope", []):
            assert scope in known, f"{code} 的 scope {scope} 不是已知命令"


def test_registered_commands_include_every_item_command():
    """确认上面那个推导真的抓到了命令 —— 否则 known 变成空集，
    整个不变量会静默失效（永远通过）。"""
    got = _registered_item_commands()
    for expected in ("item-search", "item-360", "item-profile",
                     "item-sku-list", "item-flow-source", "item-refund",
                     "spu-list", "item-relate", "video-list", "macro-monitor"):
        assert expected in got


def test_every_shown_column_is_in_the_dictionary():
    """反向不变量：每个 preset 的 show 里的每一列，都必须在 fields.json 里有
    条目、且该条目的 scope 含这个命令。

    只守 scope→命令（test_every_scope_points_to_a_real_command）是容易的方向：
    它只能发现字典里多出来的死条目，发现不了「命令在打一列字典里根本没有的
    字段」——那才是 AI 按字典取数时会踩空的方向。
    """
    fields = _load_fields()
    missing, wrong_scope = [], []
    for name, preset in sycm_item.ITEM_PRESETS.items():
        for col in preset.get("show", []):
            # 下划线开头的是 CLI 自己合成的展示列（如流量来源树的 _path），
            # 不是接口字段，不进字典。
            if col.startswith("_"):
                continue
            meta = fields.get(col)
            if meta is None:
                missing.append((name, col))
            elif name not in meta.get("scope", []):
                wrong_scope.append((name, col))
    assert not missing, f"这些展示列在 fields.json 里没有条目：{missing}"
    assert not wrong_scope, f"这些条目的 scope 漏了对应命令：{wrong_scope}"


def test_verified_entries_carry_a_note():
    fields = _load_fields()
    for code, meta in fields.items():
        if meta.get("status") == "verified":
            assert meta.get("note"), f"{code} 标了 verified 但没写 note"


# ---------- 客群洞察 item-profile ----------
#
# 接口 /cc/item/archive/profile.json 的三个硬约束（2026-08-06 实测）：
#   1. profileType 必填，白名单 10 个值，服务端会在报错里列全
#   2. crowdsType 3 个值，但只有 itmUv 回得出数据
#   3. **只认单日**。传 recent7/recent30 服务端照收 code=0，静默返空数组

PROFILE_RESPONSE = {
    "code": 0,
    "data": [
        {"statDate": {"value": "2026-08-04"}, "id": {"value": "占位人群甲"},
         "attrValue": {"value": "占位人群甲"},
         "itmUv": {"value": 250, "ratio": 0.2018},
         "attrName": {"value": "crowd"}},
        {"statDate": {"value": "2026-08-04"}, "id": {"value": "占位人群乙"},
         "attrValue": {"value": "占位人群乙"},
         "itmUv": {"value": 90, "ratio": 0.0726},
         "attrName": {"value": "crowd"}},
    ],
}


def _profile_args(**over):
    base = dict(item_id="123456789", search=None, date="2026-08-04",
                end_date=None, limit=10, page=1, raw=False, out=None,
                by="crowd", crowd="itmUv", all=False)
    base.update(over)
    return Namespace(**base)


def test_item_profile_builds_expected_params(monkeypatch):
    seen = {}

    def fake(path, params, cookies, referer=None):
        seen.update(path=path, params=params)
        return PROFILE_RESPONSE

    monkeypatch.setattr(sycm_item, "_api_get", fake)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_profile(_profile_args())
    assert seen["path"] == "/cc/item/archive/profile.json"
    assert seen["params"]["itemId"] == "123456789"
    assert seen["params"]["profileType"] == "crowd"
    assert seen["params"]["crowdsType"] == "itmUv"
    # 只认单日 —— 绝不能让区间推断把它变成 recent7
    assert seen["params"]["dateType"] == "day"
    assert seen["params"]["dateRange"] == "2026-08-04|2026-08-04"


def test_item_profile_rejects_multi_day_range(monkeypatch, capsys):
    """多日区间服务端会静默返空。宁可当场报错，也不让人看着空表猜。"""
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    called = []
    monkeypatch.setattr(sycm_item, "_api_get",
                        lambda *a, **k: called.append(1) or PROFILE_RESPONSE)
    with pytest.raises(SystemExit):
        sycm_item.cmd_item_profile(_profile_args(end_date="2026-08-05"))
    assert not called, "多日区间应当在发请求之前就被拦下"
    assert "单日" in capsys.readouterr().err


def test_item_profile_rejects_unknown_dimension(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    with pytest.raises(SystemExit):
        sycm_item.cmd_item_profile(_profile_args(by="zzz"))
    err = capsys.readouterr().err
    assert "zzz" in err
    for expected in ("crowd", "province", "purchase_level"):
        assert expected in err, "报错要把合法维度列全，别让人自己猜"


def test_item_profile_renders_share_as_percent(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: PROFILE_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_profile(_profile_args())
    out = capsys.readouterr().out
    assert "占位人群甲" in out
    assert "250" in out
    assert "20.18%" in out, "ratio 要按百分比显示，0.2018 这种裸小数没法读"


def test_item_profile_empty_cites_sample_floor_not_unknown_cause(monkeypatch, capsys):
    """payByrCnt/appSearchUv 空表的原因 2026-08-06 已查明：平台样本量门槛
    「小于 300 人不统计客群画像」。空表说明必须给出这个原因，且要点明
    「只认单日所以攒不够人数」——否则用户会去试拉长时间窗口，白试。"""
    monkeypatch.setattr(sycm_item, "_api_get",
                        lambda *a, **k: {"code": 0, "data": []})
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_profile(_profile_args(crowd="payByrCnt"))
    out = capsys.readouterr().out
    assert str(sycm_item.CROWD_SAMPLE_FLOOR) in out
    assert "样本量" in out
    assert "单日" in out, "要点明攒不够人数，别让人去试拉长窗口"
    assert "未定" not in out, "原因已查明，不该再说未定"


def test_item_profile_all_sweeps_every_dimension_with_throttle(
        monkeypatch, capsys, sleep_calls):
    seen: list[str] = []

    def fake(path, params, cookies, referer=None):
        seen.append(params["profileType"])
        return PROFILE_RESPONSE

    monkeypatch.setattr(sycm_item, "_api_get", fake)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_profile(_profile_args(all=True))
    assert seen == list(sycm_item.PROFILE_TYPES)
    assert len(sleep_calls) >= len(seen) - 1, "多请求命令必须逐个节流"


def test_profile_types_cover_server_whitelist():
    """服务端白名单（2026-08-06 实测报错原文）钉死在这里，防止漏抄。"""
    assert set(sycm_item.PROFILE_TYPES) == {
        "age", "gender", "new_old", "province", "city", "crowd",
        "brand_prefer", "cate_prefer", "purchase_level", "tq",
    }
    assert set(sycm_item.CROWD_TYPES) == {"itmUv", "payByrCnt", "appSearchUv"}


def test_item_profile_flags_dimension_with_labels_but_no_numbers(monkeypatch, capsys):
    """brand_prefer 实测会回品牌名但指标全 0 / ratio 全 null。
    直接打一列 0 会被读成「没人偏好这个品牌」，必须点明是取不到数。"""
    all_zero = {"code": 0, "data": [
        {"attrValue": {"value": "占位品牌甲"}, "itmUv": {"value": 0, "ratio": None},
         "attrName": {"value": "brand_prefer"}},
        {"attrValue": {"value": "占位品牌乙"}, "itmUv": {"value": 0, "ratio": None},
         "attrName": {"value": "brand_prefer"}},
    ]}
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: all_zero)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_profile(_profile_args(by="brand_prefer"))
    out = capsys.readouterr().out
    assert "占位品牌甲" in out, "标签本身还是要显示"
    assert "取不到" in out or "全为 0" in out


def test_item_profile_translates_verified_code_values(monkeypatch, capsys):
    """new_old 的 Y/N 已跟页面核对（2026-08-06 截图：新客户 54.97% 对上 Y）。
    补中文的同时必须保留原码，否则以后想复核找不到原值。"""
    yn = {"code": 0, "data": [
        {"attrValue": {"value": "Y"}, "itmUv": {"value": 664, "ratio": 0.5497},
         "attrName": {"value": "new_old"}},
        {"attrValue": {"value": "N"}, "itmUv": {"value": 544, "ratio": 0.4503},
         "attrName": {"value": "new_old"}},
    ]}
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: yn)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_profile(_profile_args(by="new_old"))
    out = capsys.readouterr().out
    assert "新客户(Y)" in out
    assert "老客户(N)" in out
    assert "未核" not in out, "已核对过的维度不该再打未核对警告"


def test_item_profile_says_page_is_empty_too_for_confirmed_dims(monkeypatch, capsys):
    """brand_prefer 页面上也是空的（已核对）。措辞要能区分
    「平台没这数据」和「CLI 少传参数」—— 后者是要去修的 bug。"""
    all_zero = {"code": 0, "data": [
        {"attrValue": {"value": "占位品牌甲"}, "itmUv": {"value": 0, "ratio": None},
         "attrName": {"value": "brand_prefer"}},
    ]}
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: all_zero)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_profile(_profile_args(by="brand_prefer"))
    out = capsys.readouterr().out
    assert "页面上同样是空的" in out
    assert "不是 CLI 少传参数" in out


# ---------- 潜在流失风险 item-loss-risk ----------
#
# /mc/item/customers/lossrisk.json（2026-08-06 实测，注意这是第 7 个网关族 /mc/）
#   - crowdType 必填，且**真起作用**（瞎编值回 0 条，ptl-loss 回 50 条）。
#     服务端不吐白名单，前端 bundle 里也搜不到，目前只确认了 ptl-loss 一个值。
#   - 多日区间会**静默丢掉 customerCnt 这一列**（行还在，指标没了）。

LOSS_RESPONSE = {
    "code": 0,
    "data": {
        "recordCount": 3,
        "data": [
            {"itemId": {"value": "123456789"}, "rank": {"value": 1},
             "customerCnt": {"value": 29}, "isPaidVersion": {"value": False},
             "item": {"itemId": "123456789", "title": "占位商品甲"},
             "shop": {"title": "占位本店", "shopUrl": "//a.tmall.com", "b2CShop": True}},
            {"itemId": {"value": "987654321"}, "rank": {"value": 2},
             "customerCnt": {"value": 20}, "isPaidVersion": {"value": False},
             "item": {"itemId": "987654321", "title": "占位商品乙"},
             "shop": {"title": "占位友商", "shopUrl": "//b.tmall.com", "b2CShop": True}},
            {"itemId": {"value": "111222333"}, "rank": {"value": 3},
             "customerCnt": {"value": 18}, "isPaidVersion": {"value": False},
             "item": {"itemId": "111222333", "title": "占位商品丙"},
             "shop": {"title": "占位友商", "shopUrl": "//b.tmall.com", "b2CShop": True}},
        ],
    },
}


def _loss_args(**over):
    base = dict(item_id="123456789", search=None, date="2026-08-04",
                end_date=None, limit=10, page=1, raw=False, out=None,
                crowd_type="ptl-loss")
    base.update(over)
    return Namespace(**base)


def test_item_loss_risk_builds_expected_params(monkeypatch):
    seen = {}

    def fake(path, params, cookies, referer=None):
        seen.update(path=path, params=params)
        return LOSS_RESPONSE

    monkeypatch.setattr(sycm_item, "_api_get", fake)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_loss_risk(_loss_args())
    assert seen["path"] == "/mc/item/customers/lossrisk.json"
    assert seen["params"]["crowdType"] == "ptl-loss"
    assert seen["params"]["indexCode"] == "customerCnt"
    assert seen["params"]["dateType"] == "day"


def test_item_loss_risk_renders_rank_shop_and_metric(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: LOSS_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_loss_risk(_loss_args())
    out = capsys.readouterr().out
    assert "占位商品甲" in out
    assert "占位友商" in out, "店铺列必须显示 —— 客户流去自家其它款和流去友商，是两个完全不同的问题"
    assert "29" in out


def test_item_loss_risk_summarizes_shop_spread(monkeypatch, capsys):
    """一屏 50 行看不出「多少人流向别家」。按店铺汇总一行，让人一眼看到。"""
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: LOSS_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_loss_risk(_loss_args())
    out = capsys.readouterr().out
    assert "占位友商" in out and "38" in out, "友商两行 20+18=38，要汇总出来"


def test_item_loss_risk_warns_multi_day_drops_metric(monkeypatch, capsys):
    """多日区间服务端会静默拿掉 customerCnt。行还在，容易被当成正常结果。"""
    no_metric = json.loads(json.dumps(LOSS_RESPONSE))
    for row in no_metric["data"]["data"]:
        del row["customerCnt"]
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: no_metric)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_loss_risk(
        _loss_args(date="2026-07-29", end_date="2026-08-04"))
    combined = capsys.readouterr()
    text = combined.out + combined.err
    assert "预测流失人气" in text and "单日" in text


def test_item_loss_risk_crowd_types_records_only_verified_value():
    """只确认了 ptl-loss。别为了「看起来完整」往里塞没验过的值。"""
    assert sycm_item.LOSS_CROWD_TYPES == {"ptl-loss": "潜在流失风险"}


# ---------- 详情分析 item-detail ----------
#
# 2026-08-06 从页面录到的真实参数（这几个值猜不出来，服务端对瞎编值静默返空）：
#   byrType=all、detailType=all、level1LossStatus=cate-not-pay、indexes=itemLossUvIndex
# overview 的每个指标自带 rivalAvg(同行均值) / rivalGood(同行优秀) —— 这是真的
# 同行对比，跟 item-360 那个口径不明的 *Cmpt 不是一回事。

DETAIL_OVERVIEW = {
    "code": 0,
    "data": {
        "statDate": {"value": 1785772800000},
        "itemId": {"value": "123456789"},
        "itemExposeUv": {"value": 580, "rivalAvg": 10, "rivalGood": 53,
                          "cycleCrc": 0.3144},
        "itemCartUv": {"value": 34, "rivalAvg": 2, "rivalGood": 5},
        "itemLossRate": {"value": 0.9189655172413793, "rivalAvg": 1.0,
                          "rivalGood": 0.8571},
    },
}

DETAIL_LIST = {
    "code": 0,
    "data": [
        {"detailType": {"value": "image"}, "detailTypeCn": {"value": "主图"},
         "detailLevel": {"value": 1}, "itemExposeUv": {"value": 576},
         "itemLossRate": {"value": 0.2}, "itemCartUv": {"value": 20},
         "children": [
             {"detailType": {"value": "image-video"},
              "detailTypeCn": {"value": "主图视频"},
              "detailLevel": {"value": 2}, "itemExposeUv": {"value": 436},
              "itemLossRate": {"value": 0.3}, "itemCartUv": {"value": 12}},
         ]},
        {"detailType": {"value": "eva"}, "detailTypeCn": {"value": "评价"},
         "detailLevel": {"value": 1}, "itemExposeUv": {"value": 168},
         "itemLossRate": {"value": 0.5}, "itemCartUv": {"value": 3}},
    ],
}


def _detail_args(**over):
    base = dict(item_id="123456789", search=None, date="2026-08-04",
                end_date=None, limit=20, page=1, raw=False, out=None)
    base.update(over)
    return Namespace(**base)


def test_item_detail_sends_captured_byr_type(monkeypatch):
    """byrType 猜不出来（瞎编值不报错、静默返空），必须发页面上录到的 all。"""
    seen = []

    def fake(path, params, cookies, referer=None):
        seen.append((path, params))
        return DETAIL_OVERVIEW if "overview" in path else DETAIL_LIST

    monkeypatch.setattr(sycm_item, "_api_get", fake)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_detail(_detail_args())
    assert all(p["byrType"] == "all" for _, p in seen)
    assert [p for p, _ in seen] == ["/cc/item/detail/analysis/overview.json",
                                     "/cc/item/detail/analysis/list.json"]


def test_item_detail_shows_peer_comparison(monkeypatch, capsys):
    """rivalAvg/rivalGood 是这个模块最值钱的东西 —— 光看本店数字判断不了好坏。"""
    monkeypatch.setattr(sycm_item, "_api_get",
                        lambda p, *a, **k: DETAIL_OVERVIEW if "overview" in p else DETAIL_LIST)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_detail(_detail_args())
    out = capsys.readouterr().out
    assert "同行均值" in out and "同行优秀" in out
    assert "580" in out and "53" in out


def test_item_detail_flattens_floor_children(monkeypatch, capsys):
    """楼层是两级树（主图 → 主图视频/图集/尺码）。压成一层会丢掉层级关系。"""
    monkeypatch.setattr(sycm_item, "_api_get",
                        lambda p, *a, **k: DETAIL_OVERVIEW if "overview" in p else DETAIL_LIST)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_detail(_detail_args())
    out = capsys.readouterr().out
    assert "主图" in out and "主图视频" in out
    assert "主图 > 主图视频" in out or "  主图视频" in out, "子楼层要能看出从属关系"


def test_item_detail_renders_rates_as_percent(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "_api_get",
                        lambda p, *a, **k: DETAIL_OVERVIEW if "overview" in p else DETAIL_LIST)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_detail(_detail_args())
    out = capsys.readouterr().out
    assert "91.90%" in out, "0.9189655 这种裸小数没法读"


def test_item_detail_throttles_between_requests(monkeypatch, sleep_calls):
    monkeypatch.setattr(sycm_item, "_api_get",
                        lambda p, *a, **k: DETAIL_OVERVIEW if "overview" in p else DETAIL_LIST)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_detail(_detail_args())
    assert len(sleep_calls) >= 1


# ---------- 价格分析 item-price ----------
#
# 2026-08-06 侦查（从价格分析页面 performance 记录录得）：
#   /cc/item/price/info.json      → 当前价、类目
#   /cc/item/price/getCateId.json → **本款落在哪个价格带** + 件单价
#   /mc/item/price/band/info/v3.json → 该类目各价格带的大盘（第 3 个 /mc/ 接口）
# 注意 SupplyRatioIndex 是大写 S 开头，照抄服务端，别顺手改成小写。

PRICE_INFO = {"code": 0, "data": {
    "cateId": 1629, "price": 211, "currentCategoryEdition": False,
    "cateName": "占位一级&gt;占位二级&gt;占位三级"}}

PRICE_CATE = {"code": 0, "data": {
    "cateId": 1629, "hasPermission": False, "priceSegName": "130.0-250.0",
    "priceSegId": "3", "itemUnitPrice1": 158.1038, "itemPriceSycm": 158.1}}

PRICE_BAND = {"code": 0, "data": [
    {"priceSegId": {"value": "1"}, "priceSegName": {"value": "0-65.0"},
     "payByrCnt": {"value": 6709}, "SupplyRatioIndex": {"value": 0.317},
     "tradeIndexRatio": {"value": 0.0292},
     "tradeGrowthRate": {"value": "3750% ~ 3760%"}},
    {"priceSegId": {"value": "3"}, "priceSegName": {"value": "130.0-250.0"},
     "payByrCnt": {"value": 27939}, "SupplyRatioIndex": {"value": 0.7728},
     "tradeIndexRatio": {"value": 0.4677},
     "tradeGrowthRate": {"value": "35190% ~ 35200%"}},
]}


def _price_routes(path, *a, **k):
    if "price/info" in path:
        return PRICE_INFO
    if "getCateId" in path:
        return PRICE_CATE
    if "band/info" in path:
        return PRICE_BAND
    raise AssertionError(f"没预期到的请求: {path}")


def _price_args(**over):
    base = dict(item_id="123456789", search=None, date="2026-08-04",
                end_date=None, limit=10, page=1, raw=False, out=None)
    base.update(over)
    return Namespace(**base)


def test_item_price_marks_which_band_the_item_is_in(monkeypatch, capsys):
    """整张价格带表里，本款在哪一档是唯一要一眼看到的东西。"""
    monkeypatch.setattr(sycm_item, "_api_get", _price_routes)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_price(_price_args())
    out = capsys.readouterr().out
    # 认价格带表里的行：只有表格行才带支付买家数，摘要区的「所属价格带」不带
    band_line = [l for l in out.splitlines()
                 if "130.0-250.0" in l and "27939" in l][0]
    other = [l for l in out.splitlines() if "0-65.0" in l and "6709" in l][0]
    assert "←" in band_line or "本款" in band_line
    assert "←" not in other and "本款" not in other


def test_item_price_shows_unit_price_and_listed_price(monkeypatch, capsys):
    """挂牌价和实际件单价常常差很多（活动/优惠），两个都要出。"""
    monkeypatch.setattr(sycm_item, "_api_get", _price_routes)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_price(_price_args())
    out = capsys.readouterr().out
    assert "211" in out
    assert "158.10" in out


def test_item_price_renders_ratios_as_percent(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "_api_get", _price_routes)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_price(_price_args())
    out = capsys.readouterr().out
    assert "46.77%" in out


def test_item_price_passes_growth_rate_through_unchanged(monkeypatch, capsys):
    """tradeGrowthRate 服务端直接给字符串区间，别当数字去乘 100。"""
    monkeypatch.setattr(sycm_item, "_api_get", _price_routes)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_price(_price_args())
    assert "35190% ~ 35200%" in capsys.readouterr().out


def test_item_price_throttles_between_requests(monkeypatch, sleep_calls):
    monkeypatch.setattr(sycm_item, "_api_get", _price_routes)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_price(_price_args())
    assert len(sleep_calls) >= 2, "三个接口之间都要节流"


# ---------- 标题优化 item-title ----------
#
# /cc/item/v2/getTitleWords.json 实测（2026-08-06）：没带来搜索引导的词，
# 行里**根本没有 guideSeUv 键**（不是 0，是缺列）。这类词是标题里的死字，
# 是这个模块唯一真正可执行的结论，必须单独点出来。

TITLE_WORDS = {"code": 0, "data": [
    {"searchWord": "占位词甲", "guideSeUv": {"value": 17}, "payRate": {"value": 0.0588}},
    {"searchWord": "占位词乙", "guideSeUv": {"value": 12}, "payRate": {"value": 0.0833}},
    {"searchWord": "占位死词丙"},
    {"searchWord": "占位死词丁"},
]}

TITLE_REC = {"code": 0, "data": {
    "item_id": 123456789,
    "rec_brand_words": [],
    "rec_cate_words": [
        {"word": "占位推荐甲", "score": 83.83, "hot_pctile": 0.0013,
         "compete_pctile": 0.0026, "type": 2, "reason": []},
    ],
    "rec_prop_words": [
        {"word": "占位推荐乙", "score": 70.0, "hot_pctile": 0.002,
         "compete_pctile": 0.004, "type": 3, "reason": []},
    ],
    "rec_tail_words": [],
}}


def _title_routes(path, *a, **k):
    if "getTitleWords" in path:
        return TITLE_WORDS
    if "word/recommend" in path:
        return TITLE_REC
    raise AssertionError(f"没预期到的请求: {path}")


def _title_args(**over):
    base = dict(item_id="123456789", search=None, date="2026-08-04",
                end_date=None, limit=20, page=1, raw=False, out=None)
    base.update(over)
    return Namespace(**base)


def test_item_title_counts_dead_words(monkeypatch, capsys):
    """标题里几个词是死的 —— 这是本模块唯一能直接改的东西，要算出来。"""
    monkeypatch.setattr(sycm_item, "_api_get", _title_routes)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_title(_title_args())
    out = capsys.readouterr().out
    assert "2/4" in out or "4 个词里有 2 个" in out
    assert "占位死词丙" in out and "占位死词丁" in out


def test_item_title_missing_metric_is_not_rendered_as_zero(monkeypatch, capsys):
    """零引导的词是**缺列**不是 0。渲染成 0 会让人以为有统计只是没量。"""
    monkeypatch.setattr(sycm_item, "_api_get", _title_routes)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_title(_title_args())
    dead = [l for l in capsys.readouterr().out.splitlines() if "占位死词丙" in l][0]
    assert "\t0\t" not in dead


def test_item_title_sorts_by_traffic(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "_api_get", _title_routes)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_title(_title_args())
    lines = capsys.readouterr().out.splitlines()
    i_a = next(i for i, l in enumerate(lines) if "占位词甲" in l)
    i_b = next(i for i, l in enumerate(lines) if "占位词乙" in l)
    assert i_a < i_b, "引导多的排前面"


def test_item_title_shows_recommendations_grouped(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "_api_get", _title_routes)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_title(_title_args())
    out = capsys.readouterr().out
    assert "占位推荐甲" in out and "占位推荐乙" in out
    assert "类目词" in out and "属性词" in out


def test_item_title_throttles_between_requests(monkeypatch, sleep_calls):
    monkeypatch.setattr(sycm_item, "_api_get", _title_routes)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_title(_title_args())
    assert len(sleep_calls) >= 1


# ---------- 关联搭配 item-bundle ----------
#
# /cc/item/bundle/recommend.json（系统推荐，2026-08-06 实测通，5 行）
# /cc/item/bundle/sellerRecommend.json（卖家自选，需要 orderBy；本店实测 0 行，
#   因为没手动配过搭配——空表要说明是「没配过」，不是接口坏了）

BUNDLE_SYS = {"code": 0, "data": [
    {"itemId": {"value": "987654321"}, "rank": {"value": 1},
     "bundlePayCnt": {"value": 2, "ratio": 0.3333},
     "item": {"itemId": "987654321", "title": "占位搭配商品甲"}},
    {"itemId": {"value": "111222333"}, "rank": {"value": 2},
     "bundlePayCnt": {"value": 1, "ratio": 0.1667},
     "item": {"itemId": "111222333", "title": "占位搭配商品乙"}},
]}

BUNDLE_SELLER_EMPTY = {"code": 0, "data": {"data": [], "recordCount": 0}}


def _bundle_routes(path, *a, **k):
    if "sellerRecommend" in path:
        return BUNDLE_SELLER_EMPTY
    if "bundle/recommend" in path:
        return BUNDLE_SYS
    raise AssertionError(f"没预期到的请求: {path}")


def _bundle_args(**over):
    base = dict(item_id="123456789", search=None, date="2026-08-04",
                end_date=None, limit=10, page=1, raw=False, out=None)
    base.update(over)
    return Namespace(**base)


def test_item_bundle_shows_both_lists(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "_api_get", _bundle_routes)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_bundle(_bundle_args())
    out = capsys.readouterr().out
    assert "占位搭配商品甲" in out
    assert "连带商品推荐" in out and "掌柜推荐" in out  # 页面原名


def test_item_bundle_renders_bundle_ratio(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "_api_get", _bundle_routes)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_bundle(_bundle_args())
    assert "33.33%" in capsys.readouterr().out


def test_item_bundle_empty_seller_list_says_not_configured(monkeypatch, capsys):
    """卖家自选空 = 店主没手动配过搭配，不是接口坏了。措辞要能区分。"""
    monkeypatch.setattr(sycm_item, "_api_get", _bundle_routes)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_bundle(_bundle_args())
    out = capsys.readouterr().out
    assert "没配置" in out or "未配置" in out


def test_item_bundle_seller_list_sends_order_by(monkeypatch):
    """卖家自选接口缺 orderBy 会 code=1003 拒绝。"""
    seen = []
    def fake(path, params, cookies, referer=None):
        seen.append((path, params))
        return _bundle_routes(path)
    monkeypatch.setattr(sycm_item, "_api_get", fake)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_bundle(_bundle_args())
    seller = [p for path, p in seen if "sellerRecommend" in path][0]
    assert seller.get("orderBy")
    assert seller.get("order") == "desc"


def test_item_bundle_throttles_between_requests(monkeypatch, sleep_calls):
    monkeypatch.setattr(sycm_item, "_api_get", _bundle_routes)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_bundle(_bundle_args())
    assert len(sleep_calls) >= 1


# ---------- 内容分析 item-content ----------
#
# /s_content/forcc/video/single/item/list.json（2026-08-06 从页面录得）。
# 三个猜不出来的参数：
#   keyword=<商品ID>   ← 是 keyword 不是 itemId，传 itemId 服务端不认
#   accountRole=guanghe-all
#   indexCode=<逗号分隔>  缺了返回的行没有指标列
# 页面默认走 recent30 而不是单日 —— 内容效果本来就要看长周期。
# 返回是「聚合行(videoId=all) + children 逐个视频」两层。

CONTENT_RESPONSE = {"code": 0, "data": {"recordCount": 1, "data": [
    {"videoId": {"value": "all"}, "itemTitle": {"value": "占位商品甲"},
     "contentItemClickCnt": {"value": 1364}, "contentCartItmCnt": {"value": 21.0},
     "contentCltTimes": {"value": 5}, "interestPayUV": {"value": 14},
     "interestPayAmt": {"value": 2200.0}, "itemFansClickPv": {"value": 3},
     # 实测：children 里包了一层 {data:[...]} 信封，视频行的标题是 videoTitle
     "children": [{"data": [
         {"videoId": {"value": "v1"}, "videoTitle": {"value": "占位视频甲"},
          "contentItemClickCnt": {"value": 900}, "contentCartItmCnt": {"value": 14.0},
          "contentCltTimes": {"value": 3}, "interestPayUV": {"value": 9},
          "interestPayAmt": {"value": 1400.0}, "itemFansClickPv": {"value": 2}},
     ]}]},
]}}


def _content_args(**over):
    base = dict(item_id="123456789", search=None, date="2026-07-06",
                end_date="2026-08-04", limit=10, page=1, raw=False, out=None)
    base.update(over)
    return Namespace(**base)


def test_item_content_sends_keyword_not_item_id(monkeypatch):
    """这个接口用 keyword 传商品 ID。传成 itemId 服务端不认 —— 录到的就是 keyword。"""
    seen = {}

    def fake(path, params, cookies, referer=None):
        seen.update(path=path, params=params)
        return CONTENT_RESPONSE

    monkeypatch.setattr(sycm_item, "_api_get", fake)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_content(_content_args())
    assert seen["params"]["keyword"] == "123456789"
    assert seen["params"]["accountRole"] == "guanghe-all"
    assert seen["params"]["indexCode"]
    assert "itemId" not in seen["params"]


def test_item_content_flattens_per_video_children(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: CONTENT_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_content(_content_args())
    out = capsys.readouterr().out
    assert "占位视频甲" in out
    assert "1364" in out and "900" in out


def test_item_content_labels_aggregate_row(monkeypatch, capsys):
    """videoId=all 是汇总行，混在逐个视频里会被当成某个视频重复计数。"""
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: CONTENT_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_content(_content_args())
    out = capsys.readouterr().out
    assert "合计" in out or "全部" in out


def _content_params(monkeypatch, args):
    seen = {}
    monkeypatch.setattr(sycm_item, "_api_get",
                        lambda p, params, c, referer=None: (seen.update(params), CONTENT_RESPONSE)[1])
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_content(args)
    return seen


def _span_days(date_range: str) -> int:
    start, end = date_range.split("|")
    return (date.fromisoformat(end) - date.fromisoformat(start)).days + 1


def test_item_content_defaults_to_long_window(monkeypatch):
    """内容效果看单日没意义，页面本身默认 recent30。

    2026-08-07：这个测试原来用 helper 里写死的 30 天区间，**根本没覆盖默认路径**，
    所以 date=None 时 dateType=recent30 配单日 dateRange 的 code=1003 一直没被发现。
    现在显式走 date=None。
    """
    seen = _content_params(monkeypatch, _content_args(date=None, end_date=None))
    assert seen["dateType"] == "recent30"
    assert _span_days(seen["dateRange"]) == 30


def test_item_content_date_type_always_matches_date_range(monkeypatch):
    """dateType 和 dateRange 必须同时说同一件事。

    对不上就是 code=1003 —— 服务端不会说是哪个参数错，只把两个都回给你。
    单日、7 天、30 天三档都验。
    """
    cases = [(None, None, 30), ("2026-08-06", None, 1),
             ("2026-07-31", "2026-08-06", 7), ("2026-07-08", "2026-08-06", 30)]
    for start, end, span in cases:
        seen = _content_params(monkeypatch, _content_args(date=start, end_date=end))
        assert _span_days(seen["dateRange"]) == span, (start, end, seen["dateRange"])
        expect = "day" if span == 1 else f"recent{span}"
        assert seen["dateType"] == expect, (start, end, seen["dateType"])


def test_item_content_does_not_render_envelope_as_a_row(monkeypatch, capsys):
    """children 里是 {data:[...]} 信封。当成数据行会渲染出一整行横杠。"""
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: CONTENT_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_content(_content_args())
    body = [l for l in capsys.readouterr().out.splitlines()
            if l and not l.startswith("#") and not l.startswith("内容\t")]
    assert all(l.strip("-\t") for l in body), f"有整行横杠的空行: {body}"


# ---------- 服务体验 item-service ----------
#
# /domain/oneQuery.json domainCode=tao.shop.qos.item（2026-08-06 从页面录得）
# **关键**：needCycleCrc 要放进 extMap 里，不是独立 query 参数 ——
# 当成独立参数传，服务端不报错，直接返回空 dict（8/6 上午就栽在这，
# 一度以为这个 domainCode 没数据）。
# 指标是成对的：本店值 + 同款/同行均值，所以命令按对渲染。

SERVICE_RESPONSE = {"code": 0, "data": {
    "validReplyUv": {"value": 47, "cycleCrc": -0.0208},
    "validReplyUvSameItem": {"value": 2, "cycleCrc": 0.0},
    "actRmkCnt": {"value": 2, "cycleCrc": 0.0},
    "actRmkCntSameItem": {"value": 2, "cycleCrc": 0.0},
    "wdjVocCnt": {"value": 5, "cycleCrc": 0.0},
    "wdjCateAvgVocCnt": {"value": 1, "cycleCrc": 0.0},
    "rfdSucCnt": {"value": 265, "cycleCrc": -0.0112},
}}


def _service_args(**over):
    base = dict(item_id="123456789", search=None, date="2026-07-07",
                end_date="2026-08-05", limit=20, page=1, raw=False, out=None)
    base.update(over)
    return Namespace(**base)


def test_item_service_puts_need_cycle_crc_inside_ext_map(monkeypatch):
    """needCycleCrc 必须在 extMap 里。当独立参数传服务端静默返回空 dict。"""
    seen = {}
    monkeypatch.setattr(sycm_item, "_api_get",
                        lambda p, params, c, referer=None: (seen.update(params), SERVICE_RESPONSE)[1])
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_service(_service_args())
    assert "needCycleCrc" not in seen, "不能当独立 query 参数传"
    ext = json.loads(seen["extMap"])
    assert ext["needCycleCrc"] is True
    assert ext["itemId"] == "123456789"
    assert seen["domainCode"] == "tao.shop.qos.item"


def test_item_service_pairs_own_value_with_comparison(monkeypatch, capsys):
    """光看「有效回复 47」判断不了好坏，必须和对比值并排。"""
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: SERVICE_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_service(_service_args())
    line = [l for l in capsys.readouterr().out.splitlines() if "有效接待" in l][0]
    assert "47" in line and "2" in line


def test_item_service_shows_cycle_crc(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: SERVICE_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_service(_service_args())
    assert "环比" in capsys.readouterr().out


def test_item_service_skips_metrics_the_server_did_not_return(monkeypatch, capsys):
    """服务端按权限/数据可用性少回指标是常态，缺的不该打成 0。"""
    monkeypatch.setattr(sycm_item, "_api_get",
                        lambda *a, **k: {"code": 0, "data": {
                            "validReplyUv": {"value": 47, "cycleCrc": 0.0}}})
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_service(_service_args())
    out = capsys.readouterr().out
    assert "有效接待" in out
    # 表头有「同类商品平均」，正文里不该出现没返回的指标行
    body = [l for l in out.splitlines() if l.startswith("问大家")]
    assert not body


# ========== 阶段3：页面级模块（店铺级，不带 itemId）==========
#
# 参数都是 2026-08-06 从页面 performance 记录录得，几个反直觉的点：
#   商品集   spuType=**def**（不是 all；传 all 回 "param check error"）
#   连带分析 relateOrderBy=**relatePayByrCnt**（关联侧字段带 relate 前缀），
#            且用 relateOrder 而不是 order；只传 mainOrderBy 会 code=600007
#   视频分析 detail/list 一次回 1441 条 × 33 个指标

SPU_RESPONSE = {"code": 0, "data": {"recordCount": 1, "data": [
    {"spuId": {"value": 45349}, "spuName": {"value": "占位商品集甲"},
     "spuTypeCn": {"value": "自定义"}, "spuItemCnt": {"value": 3},
     "spuPayOrdAmt": {"value": 3888.84, "cycleCrc": 0.0151},
     "spuPayOrdItmQty": {"value": 26, "cycleCrc": 0.04},
     "spuUnitPrice": {"value": 149.57}},
]}}

RELATE_RESPONSE = {"code": 0, "data": {"data": [
    {"itemId": {"value": "123456789"}, "item": {"title": "占位主商品甲"},
     "uv": {"value": 500}, "payAmt": {"value": 9000.0},
     "payItemCnt": {"value": 60}, "payByrCnt": {"value": 55},
     "cartByrCnt": {"value": 120},
     "relateItems": [
         {"itemId": {"value": "987654321"}, "mainItemId": {"value": "123456789"},
          "item": {"title": "占位关联商品乙"},
          "relatePayByrCnt": {"value": 8}, "relatePayByrRate": {"value": 0.1455},
          "relateUv": {"value": 90}, "relateUvRate": {"value": 0.18},
          "relateCartByrCnt": {"value": 20}, "relateCartByrRate": {"value": 0.1667}},
     ]},
]}}

VIDEO_RESPONSE = {"code": 0, "data": {"recordCount": 2, "data": [
    {"itemId": {"value": "123456789"}, "item": {"title": "占位视频商品甲"},
     "itemExposeUv": {"value": 10091}, "itemClkUv": {"value": 4095},
     "exposureClickRate": {"value": 0.4058}, "validPlayUv": {"value": 1472},
     "effectivePlayRate": {"value": 0.4748}, "completionRateNew": {"value": 0.093},
     "daysDealUv": {"value": 12}, "daysPayAmt": {"value": 2026.1}},
]}}


def _page_args(**over):
    base = dict(date="2026-07-29", end_date="2026-08-04", limit=10, page=1,
                raw=False, out=None)
    base.update(over)
    return Namespace(**base)


def test_spu_list_sends_spu_type_def(monkeypatch):
    """spuType=def 是从页面录的；传 all 服务端只回一句 param check error。"""
    seen = {}
    monkeypatch.setattr(sycm_item, "_api_get",
                        lambda p, params, c, referer=None: (seen.update(params), SPU_RESPONSE)[1])
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_spu_list(_page_args(date="2026-08-04", end_date="2026-08-04"))
    assert seen["spuType"] == "def"
    assert seen["indexCode"]


def test_spu_list_renders_rows(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: SPU_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_spu_list(_page_args(date="2026-08-04", end_date="2026-08-04"))
    out = capsys.readouterr().out
    assert "占位商品集甲" in out and "3888.84" in out


def test_item_relate_sends_both_order_params(monkeypatch):
    """只传 mainOrderBy 会 code=600007；关联侧字段名带 relate 前缀。"""
    seen = {}
    monkeypatch.setattr(sycm_item, "_api_get",
                        lambda p, params, c, referer=None: (seen.update(params), RELATE_RESPONSE)[1])
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_relate(_page_args())
    assert seen["mainOrderBy"] and seen["relateOrderBy"].startswith("relate")
    assert seen["relateOrder"] == "desc"


def test_item_relate_rejects_single_day_locally(monkeypatch):
    """单日必挂：服务端只回 code=1002 "4004:"，一个字都不提日期。本地先拦。"""
    called = []
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: called.append(1))
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    with pytest.raises(SystemExit):
        sycm_item.cmd_item_relate(_page_args(date="2026-08-06", end_date=None))
    assert not called, "拦截失败，还是打了网络"


def test_item_relate_default_window_is_not_a_single_day():
    """默认参数必须能直接跑通。

    2026-08-07：默认是「昨天单日」，也就是**默认调用必挂**。当初核验用的是手敲的
    7 天窗口，恰好绕开了默认路径。改成默认近 7 天。
    """
    import argparse
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    sycm_item.register(sub, "2026-08-06")
    ns = parser.parse_args(["item-relate"])
    assert ns.date != ns.end_date, "默认还是单日，跑起来必挂"
    span = (date.fromisoformat(ns.end_date) - date.fromisoformat(ns.date)).days + 1
    assert span == 7


def test_item_relate_nests_related_under_main(monkeypatch, capsys):
    """主商品和它的关联商品要能看出从属，平铺就没法读了。"""
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: RELATE_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_relate(_page_args())
    lines = capsys.readouterr().out.splitlines()
    i_main = next(i for i, l in enumerate(lines) if "占位主商品甲" in l)
    i_rel = next(i for i, l in enumerate(lines) if "占位关联商品乙" in l)
    assert i_main < i_rel
    assert lines[i_rel].startswith(("  ", "\t", "└", "├")), "关联行要缩进"


def test_video_list_renders_key_metrics(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: VIDEO_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_video_list(_page_args())
    out = capsys.readouterr().out
    assert "10091" in out and "40.58%" in out and "2026.10" in out


def test_video_list_reports_total_not_just_page(monkeypatch, capsys):
    """实测 1441 条，默认只显示一页。不报总数会让人以为就这么几条。"""
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: VIDEO_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_video_list(_page_args())
    assert "共 2" in capsys.readouterr().out


def test_spu_list_rejects_multi_day_range(monkeypatch, capsys):
    """商品集只认单日。服务端只回 "param check error"，指不到日期上，
    所以在发请求前就拦掉并说清原因。"""
    called = []
    monkeypatch.setattr(sycm_item, "_api_get",
                        lambda *a, **k: called.append(1) or SPU_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    with pytest.raises(SystemExit):
        sycm_item.cmd_spu_list(_page_args(date="2026-07-29", end_date="2026-08-04"))
    assert not called
    assert "单日" in capsys.readouterr().err


# ---------- 宏观监控 macro-monitor ----------
#
# /cc/cockpit/marcro/core/live/overview.json 是 **实时快照**（响应带 updateTime
# 与 interval=60）。2026-08-06 实测：recent7 / recent30 / day 三档返回的
# payAmt 完全相同（访客数的微小差异只是实时数在跳）—— **--date 不生效**。
# 不说清楚就是又一个「看着有数、其实答非所问」的坑。

MACRO_RESPONSE = {"code": 0, "data": {
    "updateTime": "2026-08-06 12:58:07", "interval": 60,
    "data": {
        "payAmt": {"value": 11757.95, "cycleCrc": -0.3003},
        "itmUv": {"value": 12227, "cycleCrc": 0.0025},
        "payRate": {"value": 0.0067, "cycleCrc": -0.2284},
        "visitCartRate": {"value": 0.0409, "cycleCrc": -0.1142},
    }}}


def test_macro_monitor_warns_date_is_ignored(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: MACRO_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_macro_monitor(_page_args())
    combined = capsys.readouterr()
    text = combined.out + combined.err
    assert "实时" in text
    assert "不生效" in text or "忽略" in text


def test_macro_monitor_shows_update_time(monkeypatch, capsys):
    """实时数据必须显示服务端的更新时刻，否则没法判断数据新旧。"""
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: MACRO_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_macro_monitor(_page_args())
    assert "2026-08-06 12:58:07" in capsys.readouterr().out


def test_macro_monitor_renders_rates_as_percent(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: MACRO_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_macro_monitor(_page_args())
    out = capsys.readouterr().out
    assert "0.67%" in out and "4.09%" in out


# ---------- 问题预警 problem-alarm ----------
#
# /cc/prolemitem/statistics.json —— 服务端把 problem 拼成 **prolem**，照抄不改。
# 实时接口（updateTime + interval=30）。
# 「质量问题商品」在页面上点进去只显示「请在新打开的页面中查看」，跳出 sycm
# 去别的系统 —— sycm 侧只有计数、拿不到那几个商品是哪几个，必须说明白，
# 否则用户会以为 CLI 少做了一块。

ALARM_STATS = {"code": 0, "data": {
    "updateTime": "2026-08-06 13:03:02", "interval": 30,
    "data": {"qualityIssueItemCnt": 5, "total": 5,
             "highPriceItemCnt": 0, "stockoutItemCnt": 0}}}

ALARM_STOCKOUT = {"code": 0, "data": {
    "updateTime": "2026-08-06 13:03:05", "interval": 3600, "data": []}}


def _alarm_routes(path, *a, **k):
    if "statistics" in path:
        return ALARM_STATS
    if "stock/out" in path:
        return ALARM_STOCKOUT
    raise AssertionError(f"没预期到的请求: {path}")


def test_problem_alarm_shows_three_counts(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "_api_get", _alarm_routes)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_problem_alarm(_page_args())
    out = capsys.readouterr().out
    assert "质量问题商品" in out and "5" in out
    assert "缺货商品" in out and "高价限流商品" in out


def test_problem_alarm_says_quality_detail_lives_outside_sycm(monkeypatch, capsys):
    """有计数但拿不到明细，是平台把明细放在别的系统了，不是 CLI 少做。"""
    monkeypatch.setattr(sycm_item, "_api_get", _alarm_routes)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_problem_alarm(_page_args())
    out = capsys.readouterr().out
    assert "明细" in out and ("不在 sycm" in out or "跳出" in out)


def test_problem_alarm_shows_update_time(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "_api_get", _alarm_routes)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_problem_alarm(_page_args())
    assert "2026-08-06 13:03:02" in capsys.readouterr().out


def test_problem_alarm_empty_stockout_is_good_news(monkeypatch, capsys):
    """缺货 0 条是好事，不能渲染成一个让人以为出错的空表。"""
    monkeypatch.setattr(sycm_item, "_api_get", _alarm_routes)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_problem_alarm(_page_args())
    out = capsys.readouterr().out
    assert "没有缺货" in out or "无缺货" in out


# ---------- 商品区间分析 interval-analysis ----------
#
# /cc/interval/list.json（2026-08-06 从宏观监控的「商品区间分析」子 tab 录得）
# defAnalyseType 三个视角：ordPqt=按价格带 / payItmCnt=按支付件数 / payAmt=按支付金额
# **空区间的行只有 band 一个键，没有任何指标** —— 跟标题死词同一个模式，
# 必须打 "-"，打 0 会被读成「这个区间有商品但卖了 0 元」。

INTERVAL_RESPONSE = {"code": 0, "data": [
    {"band": "0-45"},                       # 空区间：只有 band，没有指标
    {"band": "45-", "statDate": {"value": "2026-08-04"},
     "paidItemCnt": {"value": 171, "ratio": 1.0},
     "payAmt": {"value": 36560.85, "ratio": 1.0},
     "payItmCnt": {"value": 285, "ratio": 1.0},
     "ordPqt": {"value": 128.28, "ratio": 1.0}},
]}


def test_interval_analysis_empty_band_is_dash_not_zero(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: INTERVAL_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_interval_analysis(_page_args(by="ordPqt", end_date=None))
    empty = [l for l in capsys.readouterr().out.splitlines() if l.startswith("0-45")][0]
    assert "\t0\t" not in empty and "0.00%" not in empty
    assert "-" in empty


def test_interval_analysis_shows_share(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: INTERVAL_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_interval_analysis(_page_args(by="ordPqt", end_date=None))
    out = capsys.readouterr().out
    assert "171" in out and "100.00%" in out and "36560.85" in out


def test_interval_analysis_rejects_unknown_view(monkeypatch, capsys):
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    with pytest.raises(SystemExit):
        sycm_item.cmd_interval_analysis(_page_args(by="zzz"))
    err = capsys.readouterr().err
    for v in ("ordPqt", "payItmCnt", "payAmt"):
        assert v in err


def test_interval_analysis_sends_view_as_def_analyse_type(monkeypatch):
    seen = {}
    monkeypatch.setattr(sycm_item, "_api_get",
                        lambda p, params, c, referer=None: (seen.update(params), INTERVAL_RESPONSE)[1])
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_interval_analysis(_page_args(by="payAmt"))
    assert seen["defAnalyseType"] == "payAmt"
    assert seen["indexCode"]


def test_refund_reason_pins_interval_level_to_99():
    """rfdIntervalLevel 必须是 99。这个值曾被猜成 "ALL" —— 服务端照收、
    不报错、静默返回空列表，害这张表空了两天。钉死，不许再改回猜的值。"""
    preset = sycm_item.ITEM_PRESETS["item-refund-reason"]
    assert preset["extra_params"]["rfdIntervalLevel"] == "99"


def test_refund_reason_shows_chinese_name_and_real_amount_field():
    """show 里必须用 rfdReasonNameCn（中文）和 itemRfdAmt（真实金额字段）。
    itemSucRfdAmt 在响应里不存在，用它会整列打空。"""
    show = sycm_item.ITEM_PRESETS["item-refund-reason"]["show"]
    assert "rfdReasonNameCn" in show and "itemRfdAmt" in show
    assert "itemSucRfdAmt" not in show


def test_item_content_states_which_page_tab_it_covers(monkeypatch, capsys):
    """必须说清只覆盖「TOP短视频」标签。

    2026-08-07：此前这里断言的是「商品点击次数与页面对不上」的警告。
    页面截图逐格比对后结案 —— 7 行 × 5 列 35 个格子全中，字段没问题。
    当初对不上是**比错了对象**：页面这一块有 TOP直播 / TOP短视频 / TOP图文
    三个标签，本命令走的 video 接口只对应短视频那一个。
    所以现在要提示的不是「数不准」，而是「别拿另一个标签的数来对」。
    """
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: CONTENT_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_item_content(_content_args())
    out = capsys.readouterr().out
    assert "TOP短视频" in out
    # 已结案的旧警告不能再出现，否则等于继续误导
    assert "未查明" not in out


def test_interval_analysis_omits_meaningless_unit_price_share(capsys, monkeypatch):
    """件单价不该有「占比」——那是拿两档单价相加当分母算的，没有业务含义，
    页面上也没有这一列（2026-08-06 核对）。"""
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: INTERVAL_RESPONSE)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_interval_analysis(_page_args(by="ordPqt", end_date=None))
    lines = capsys.readouterr().out.splitlines()
    header = [l for l in lines if l.startswith("区间")][0]
    assert header.count("占比") == 3, "只有动销商品数/支付金额/支付件数三列有占比"
    row = [l for l in lines if l.startswith("45-")][0]
    assert row.rstrip().endswith("128.28"), "件单价应是最后一列且不带占比"


def test_refund_reason_shows_loss_to_rival_count():
    """流失至竞店人数比单纯的退款人数更有指向性：退了还留在店里、和退了
    直接去买别家，是两回事。2026-08-06 与页面同名列核对一致。"""
    assert "lossByrCnt" in sycm_item.ITEM_PRESETS["item-refund-reason"]["show"]


def test_item_360_renders_rates_as_percent(monkeypatch, capsys):
    """核心指标里的比率此前打的是 0.0066280033... 这种裸小数，没法读。
    判据用字段名后缀 Rate —— 中文名没跟页面核过，不猜也不写。"""
    core = {"code": 0, "data": {
        "payRate": {"value": 0.006628003314001657},
        "payRateCrc": {"value": 0.2161},
        "uv": {"value": 1207},
        "itemUvCrc": {"value": -0.2292},
    }}
    monkeypatch.setattr(sycm_item, "_api_get",
                        lambda p, *a, **k: core if "coreIndex" in p
                        else {"code": 0, "data": {"fCharge": {"value": 158.95}}})
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    args = Namespace(item_id="123456789", search=None, date="2026-08-04",
                     end_date=None, limit=10, page=1, raw=False, out=None)
    sycm_item.cmd_item_360(args)
    out = capsys.readouterr().out
    assert "0.66%" in out
    assert "0.006628003314001657" not in out


def test_loss_risk_empty_is_not_reported_as_a_date_problem(monkeypatch, capsys):
    """0 行 ≠ 日期传错了。

    2026-08-07：`has_metric = any(...)` 在 rows 为空时也是 False，于是「这个款
    压根没数据」被误报成「多日区间服务端丢了指标，请改单日」。用户照着改日期
    只会白折腾。两种情况必须分开说。
    """
    monkeypatch.setattr(sycm_item, "_api_get",
                        lambda *a, **k: {"data": {"data": [], "recordCount": 0}})
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    monkeypatch.setattr(sycm_item, "resolve_item_id", lambda *a, **k: "123456789")
    sycm_item.cmd_item_loss_risk(Namespace(
        item_id="123456789", search=None, date="2026-08-06", end_date=None,
        limit=10, page=1, raw=False, out=None, crowd_type="ptl-loss"))
    out = capsys.readouterr().out
    assert "多日区间" not in out, "空结果被误报成日期问题"
    assert "无数据" in out


# ── 退款 SKU 表的服务端分页上限（2026-08-07 取证）────────────────────────
# /cc/refund/item/sku/list.json 每页最多回 5 行，pageSize 传 100 也只给 5。
# 实测：recordCount=12，pageSize=100 → 5 行；pageSize=5 翻三页 → 5+5+2=12 行。
# 我们不翻页，还把「本页行数」当「总行数」打印，于是 12 个 SKU 只显示 5 个，
# 表头却写「共 5 行」—— 看的人根本不知道少了 7 个。

def _capped_sku_server(record_count=12, per_page=5):
    """模拟服务端：每页最多 per_page 行，无视更大的 pageSize。"""
    calls = []

    def fake(path, params, cookies, referer=None):
        if "reason" in path:
            return {"data": []}          # 退款原因接口的 data 是裸列表
        if "refund/item/sku" not in path:
            return {"data": {"data": [], "recordCount": 0}}
        page = int(params.get("page", 1))
        start = (page - 1) * per_page
        rows = [{"skuName": f"尺码:{i}", "itemSkuSucRfdByr": 1,
                 "itemSkuRfdAmt": 10.0, "payAmtRfdRate": 0.1, "ordRfdRate": 0.1}
                for i in range(start, min(start + per_page, record_count))]
        calls.append((page, params.get("pageSize"), len(rows)))
        return {"data": {"data": rows, "recordCount": record_count}}

    return fake, calls


def test_refund_sku_table_pages_through_server_side_cap(monkeypatch, capsys):
    """服务端每页封顶 5 行时，--limit 20 必须翻页取满，不能只给 5 行。"""
    fake, calls = _capped_sku_server()
    monkeypatch.setattr(sycm_item, "_api_get", fake)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    monkeypatch.setattr(sycm_item, "resolve_item_id", lambda *a, **k: "123456789")
    monkeypatch.setattr(sycm_item, "_sleep_humanlike", lambda *a, **k: None)
    sycm_item.cmd_item_refund(Namespace(
        item_id="123456789", search=None, date="2026-07-08",
        end_date="2026-08-06", limit=20, page=1, raw=False, out=None))
    out = capsys.readouterr().out
    sku_block = out.split("各 SKU 退款")[1]
    shown = [l for l in sku_block.splitlines() if l.startswith("尺码:")]
    assert len(shown) == 12, f"只取到 {len(shown)} 行，服务端有 12 行"
    assert len([c for c in calls if c[0] > 1]) >= 2, f"没翻页，请求记录={calls}"


def test_refund_table_header_reports_server_total_not_page_size(monkeypatch, capsys):
    """表头不能拿「本页行数」冒充「总行数」。

    --limit 3 时服务端有 12 行，表头必须让人看出总共 12 行、这里只显示 3 行。
    """
    fake, _ = _capped_sku_server()
    monkeypatch.setattr(sycm_item, "_api_get", fake)
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    monkeypatch.setattr(sycm_item, "resolve_item_id", lambda *a, **k: "123456789")
    monkeypatch.setattr(sycm_item, "_sleep_humanlike", lambda *a, **k: None)
    sycm_item.cmd_item_refund(Namespace(
        item_id="123456789", search=None, date="2026-07-08",
        end_date="2026-08-06", limit=3, page=1, raw=False, out=None))
    header = [l for l in capsys.readouterr().out.splitlines()
              if "各 SKU 退款" in l][0]
    assert "12" in header, f"表头没说总共 12 行: {header!r}"


def test_refund_reason_rows_are_flagged_as_non_additive(monkeypatch, capsys):
    """退款原因各行不可相加。

    2026-08-07 取证：rfdIdentifyType=alg_identify 会给一笔退款打多个原因标签。
    实测同款同窗口：原因表退款单数合计 168，属性表只有 122，分母 payOrdCnt
    两张表都是 211。所以「按原因求和」会重复计数，不能当唯一人数用。
    """
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    monkeypatch.setattr(sycm_item, "resolve_item_id", lambda *a, **k: "123456789")
    monkeypatch.setattr(sycm_item, "_sleep_humanlike", lambda *a, **k: None)
    monkeypatch.setattr(sycm_item, "_api_get", lambda path, *a, **k: (
        {"data": [{"rfdReasonTypeCn": {"value": "内部原因"},
                   "rfdReasonNameCn": {"value": "商品问题"},
                   "itemSucRfdByr": {"value": 56}, "lossByrCnt": {"value": 14},
                   "itemRfdAmt": {"value": 9226.35},
                   "payAmtRfdRate": {"value": 0.29}}]}
        if "reason" in path else {"data": {"data": [], "recordCount": 0}}))
    sycm_item.cmd_item_refund(Namespace(
        item_id="123456789", search=None, date="2026-07-08",
        end_date="2026-08-06", limit=10, page=1, raw=False, out=None))
    out = capsys.readouterr().out
    assert "不可相加" in out or "不能相加" in out, "没提示各行不可相加"


# ── 区间分析：坏分档要说出来，别装成有效区间（2026-08-07 取证）────────────

def _interval_args(**over):
    base = dict(date="2026-08-06", end_date=None, by="ordPqt", limit=10,
                page=1, raw=False, out=None)
    base.update(over)
    return Namespace(**base)


def test_interval_flags_degenerate_bands(monkeypatch, capsys):
    """payItmCnt 视角服务端恒回两行完全相同的行，必须明说这不是有效分档。"""
    dup = {"band": "0-", "paidItemCnt": {"value": 155, "ratio": 0.5},
           "payAmt": {"value": 30566.14, "ratio": 0.5},
           "payItmCnt": {"value": 237, "ratio": 0.5},
           "ordPqt": {"value": 128.97, "ratio": 0.5}}
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: {"data": [dup, dict(dup)]})
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_interval_analysis(_interval_args(by="payItmCnt"))
    out = capsys.readouterr().out
    assert "区间没配好" in out and "编辑" in out


def test_interval_does_not_flag_real_bands(monkeypatch, capsys):
    """正常分档不能误报。"""
    rows = [{"band": "0-67", "paidItemCnt": {"value": 6, "ratio": 0.0387},
             "payAmt": {"value": 343.66, "ratio": 0.011},
             "payItmCnt": {"value": 6, "ratio": 0.025},
             "ordPqt": {"value": 57.28}},
            {"band": "67-", "paidItemCnt": {"value": 149, "ratio": 0.961},
             "payAmt": {"value": 30222.48, "ratio": 0.988},
             "payItmCnt": {"value": 231, "ratio": 0.974},
             "ordPqt": {"value": 130.83}}]
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: {"data": rows})
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    sycm_item.cmd_interval_analysis(_interval_args())
    assert "区间没配好" not in capsys.readouterr().out


def test_interval_price_view_rejects_multi_day_locally(monkeypatch):
    """价格带视角 7/30 天窗口服务端都回 code=1002 "4000:"，不提日期。本地先拦。"""
    called = []
    monkeypatch.setattr(sycm_item, "_api_get", lambda *a, **k: called.append(1))
    monkeypatch.setattr(sycm_item, "load_taobao_cookies", lambda: {"_tb_token_": "tok"})
    with pytest.raises(SystemExit):
        sycm_item.cmd_interval_analysis(
            _interval_args(date="2026-07-31", end_date="2026-08-06"))
    assert not called, "拦截失败，还是打了网络"


def test_fetch_item_rows_says_so_when_it_hits_the_page_cap(monkeypatch, capsys):
    """撞上本地翻页上限要明说，不能让表头继续建议「加 --limit」。

    服务端每页 5 行、recordCount=500 时，翻满 _MAX_PAGES 也只有 30 行。
    这时表头那句「要全部请加 --limit 500」是假指路。
    """
    def fake(path, params, cookies, referer=None):
        page = int(params.get("page", 1))
        rows = [{"skuName": f"s{page}-{i}"} for i in range(5)]
        return {"data": {"data": rows, "recordCount": 500}}

    monkeypatch.setattr(sycm_item, "_api_get", fake)
    monkeypatch.setattr(sycm_item, "_sleep_humanlike", lambda *a, **k: None)
    rows, total = sycm_item.fetch_item_rows(
        "item-refund-sku", item_id="123456789", start_date="2026-07-08",
        end_date="2026-08-06", want=500, cookies={"_tb_token_": "tok"},
        sleep_first=False)
    assert len(rows) == 5 * sycm_item._MAX_PAGES
    assert total == 500
    assert "翻页上限" in capsys.readouterr().err


def test_fetch_item_rows_is_quiet_when_it_gets_everything(monkeypatch, capsys):
    """正常取全时不能刷这条提示。"""
    def fake(path, params, cookies, referer=None):
        page = int(params.get("page", 1))
        start = (page - 1) * 5
        rows = [{"skuName": f"s{i}"} for i in range(start, min(start + 5, 12))]
        return {"data": {"data": rows, "recordCount": 12}}

    monkeypatch.setattr(sycm_item, "_api_get", fake)
    monkeypatch.setattr(sycm_item, "_sleep_humanlike", lambda *a, **k: None)
    rows, _ = sycm_item.fetch_item_rows(
        "item-refund-sku", item_id="123456789", start_date="2026-07-08",
        end_date="2026-08-06", want=20, cookies={"_tb_token_": "tok"},
        sleep_first=False)
    assert len(rows) == 12
    assert "翻页上限" not in capsys.readouterr().err
