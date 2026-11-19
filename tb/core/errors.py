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
        # 建出来就记一笔：各平台的命令行自己接住错误、打印、返回退出码，总入口看不到它们
        from . import runlog
        runlog.event("error", type=type(self).__name__, message=runlog._clean(message), endpoint=endpoint, stage=stage,
                     hint=runlog._clean(hint) if hint else "")


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


class AccountChanged(TbError):
    """取数途中浏览器里登录的账号换了（别的命令或有人在插件里切换了账号）：这次的数据可能混进了别的账号，作废。"""
    exit_code = 1


class ShopChanged(TbError):
    """同一条命令里先后拿到了两家店的数据：作废。"""
    exit_code = 1


class PluginChanged(TbError):
    """一条命令的请求被两个不同的取数桥插件实例接了（几个浏览器 / Chrome 资料都装了插件，登录的可能是不同的店）：作废。"""
    exit_code = 1
