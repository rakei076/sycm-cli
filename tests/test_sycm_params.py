import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sycm_cli


def test_build_params_sycm_v1_shape():
    preset = {"param_style": "sycm-v1", "orderBy": "startTime"}
    got = sycm_cli.build_query_params(
        preset, start_date="2026-08-01", end_date="2026-08-01",
        page_no=1, page_size=10, token="tok",
    )
    assert got == {
        "token": "tok",
        "startDate": "20260801",
        "endDate": "20260801",
        "dateType": "day",
        "dateRange": "day",
        "orderBy": "startTime",
        "pageNo": "1",
        "pageSize": "10",
    }


def test_build_params_cc_v2_shape_single_day():
    preset = {"param_style": "cc-v2", "orderBy": "payAmt", "indexCode": "itmUv,payAmt"}
    got = sycm_cli.build_query_params(
        preset, start_date="2026-08-01", end_date="2026-08-01",
        page_no=2, page_size=5, token="tok",
    )
    assert got == {
        "token": "tok",
        "dateRange": "2026-08-01|2026-08-01",
        "dateType": "day",
        "page": "2",
        "pageSize": "5",
        "order": "desc",
        "orderBy": "payAmt",
        "indexCode": "itmUv,payAmt",
    }


def test_build_params_cc_v2_infers_recent7():
    preset = {"param_style": "cc-v2", "orderBy": "payAmt"}
    got = sycm_cli.build_query_params(
        preset, start_date="2026-07-29", end_date="2026-08-04",
        page_no=1, page_size=10, token="tok",
    )
    assert got["dateType"] == "recent7"
    assert got["dateRange"] == "2026-07-29|2026-08-04"


def test_build_params_cc_v2_rejects_unsupported_window():
    """实测（2026-08-05）：10 天窗口不论 dateType 传 day 还是 recent10，
    coreIndex / 退款 / 流量来源三个接口都以 code=1003 拒绝。
    与其静默回落成 day 发一个必然失败的请求，不如在客户端先报清楚。"""
    preset = {"param_style": "cc-v2", "orderBy": "payAmt"}
    with pytest.raises(ValueError, match="7/15/30"):
        sycm_cli.build_query_params(
            preset, start_date="2026-07-01", end_date="2026-07-10",
            page_no=1, page_size=10, token="tok",
        )


@pytest.mark.parametrize("start,end,expect", [
    ("2026-08-04", "2026-08-04", "day"),
    ("2026-07-29", "2026-08-04", "recent7"),
    ("2026-07-21", "2026-08-04", "recent15"),
    ("2026-07-06", "2026-08-04", "recent30"),
])
def test_infer_cc_date_type_supported_windows(start, end, expect):
    assert sycm_cli._infer_cc_date_type(start, end) == expect


def test_infer_cc_date_type_rejects_bad_date_format():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        sycm_cli._infer_cc_date_type("2026/07/01", "2026/07/07")


def test_build_params_default_date_type_bypasses_window_check():
    """preset 显式声明 default_date_type 时不做窗口推断（留给未来确有需要的接口）。"""
    preset = {"param_style": "cc-v2", "orderBy": "payAmt",
              "default_date_type": "recent7"}
    got = sycm_cli.build_query_params(
        preset, start_date="2026-07-01", end_date="2026-07-10",
        page_no=1, page_size=10, token="tok",
    )
    assert got["dateType"] == "recent7"


def test_build_params_extra_params_and_extra_arg_merge():
    preset = {"param_style": "cc-v2", "orderBy": "payAmt",
              "extra_params": {"cateType": "std"}}
    got = sycm_cli.build_query_params(
        preset, start_date="2026-08-01", end_date="2026-08-01",
        page_no=1, page_size=10, token="tok", extra={"itemId": "123456789"},
    )
    assert got["cateType"] == "std"
    assert got["itemId"] == "123456789"


def test_build_params_sycm_v1_with_extra_params():
    """回归：extra_params 必须对 sycm-v1 也生效，不能只在 cc-v2 里生效。"""
    preset = {"param_style": "sycm-v1", "orderBy": "startTime",
              "extra_params": {"customField": "customValue"}}
    got = sycm_cli.build_query_params(
        preset, start_date="2026-08-01", end_date="2026-08-01",
        page_no=1, page_size=10, token="tok",
    )
    assert got["customField"] == "customValue"
    assert got["orderBy"] == "startTime"


def test_build_params_sycm_v1_extra_params_and_extra_collision():
    """键冲突时 extra 参数覆盖 preset 的 extra_params。"""
    preset = {"param_style": "sycm-v1", "orderBy": "startTime",
              "extra_params": {"customField": "preset_value", "presetOnly": "p1"}}
    got = sycm_cli.build_query_params(
        preset, start_date="2026-08-01", end_date="2026-08-01",
        page_no=1, page_size=10, token="tok",
        extra={"customField": "arg_value", "argOnly": "a1"},
    )
    # 冲突时 extra 赢
    assert got["customField"] == "arg_value"
    # 两边独有的键都要在
    assert got["presetOnly"] == "p1"
    assert got["argOnly"] == "a1"


def test_build_params_flow_source_preset():
    """流量来源(/flow/*)接口的实际参数：与 /cc/* 同一套拼法，差异全在 extra_params。"""
    preset = {
        "param_style": "cc-v2", "orderBy": "uv",
        "indexCode": "uv,cltItmCnt,cartByrCnt,payByrCnt",
        "extra_params": {"flowBizType": "classic",
                          "activateBoost": "sourceChannel", "crowdType": "all"},
    }
    got = sycm_cli.build_query_params(
        preset, start_date="2026-08-01", end_date="2026-08-01",
        page_no=1, page_size=10, token="tok", extra={"itemId": "123456789"},
    )
    assert got == {
        "token": "tok",
        "dateRange": "2026-08-01|2026-08-01",
        "dateType": "day",
        "page": "1",
        "pageSize": "10",
        "order": "desc",
        "orderBy": "uv",
        "indexCode": "uv,cltItmCnt,cartByrCnt,payByrCnt",
        "flowBizType": "classic",
        "activateBoost": "sourceChannel",
        "crowdType": "all",
        "itemId": "123456789",
    }


def test_build_params_refund_preset():
    """退款(/csp/api/*、/cc/refund/*)接口的实际参数：同上，同一套拼法。"""
    preset = {
        "param_style": "cc-v2", "orderBy": "itemSucRfdByr",
        "extra_params": {"refundDateType": "pay", "caseScene": "ALL"},
    }
    got = sycm_cli.build_query_params(
        preset, start_date="2026-07-06", end_date="2026-08-04",
        page_no=1, page_size=10, token="tok", extra={"itemId": "123456789"},
    )
    assert got == {
        "token": "tok",
        "dateRange": "2026-07-06|2026-08-04",
        "dateType": "recent30",
        "page": "1",
        "pageSize": "10",
        "order": "desc",
        "orderBy": "itemSucRfdByr",
        "refundDateType": "pay",
        "caseScene": "ALL",
        "itemId": "123456789",
    }
