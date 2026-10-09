"""统一的错误类型。退出码：1 = 一般失败，2 = 登录失效，3 = 触发风控。"""
from __future__ import annotations


class TbError(RuntimeError):
    exit_code = 1

    def __init__(self, message: str, *, endpoint: str = "", stage: str = "", hint: str = ""):
        self.endpoint, self.stage, self.hint = endpoint, stage, hint
        parts = [message]
        if endpoint:
            parts.append(f"接口：{endpoint}")
        if stage:
            parts.append(f"阶段：{stage}")
        if hint:
            parts.append(f"建议：{hint}")
        super().__init__("\n".join(parts))


class RetryRequest(Exception):
    """平台钩子（check_payload）要求用重新构造的请求再发一次（如 mtop 令牌换发后重签）。不是错误，不会传到命令行。"""


class LoginExpired(TbError):
    exit_code = 2


class ApiFailed(TbError):
    exit_code = 1


class EmptyResult(TbError):
    exit_code = 1


class RiskStopped(TbError):
    exit_code = 3


class Redirected(TbError):
    """平台没回数据，而是把请求转去了别的页面（排队页或登录页）。按「被平台拦截」处理。"""
    exit_code = 3


class WriteBlocked(TbError):
    exit_code = 1
