"""脚本执行路径（python sycm_cli.py …）的护栏契约测试。

其余测试全部走 `import sycm_cli`，那条路径上 sycm_cli 只被加载一份，看不见
「主脚本是 __main__、sycm_item 又按名字加载第二份 sycm_cli」导致的类身份分裂。
文档公示的跑法恰恰是脚本方式，风控退出码 2 是护栏的唯一对外信号，必须钉死。

不打网络：子进程在 runpy 之前把 curl_cffi / browser_cookie3 换成假模块，
任何请求都返回带风控词「滑块」的响应。
"""
import subprocess  # nosec B404 — 固定参数列表，不过 shell
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]

# 子进程脚本：完全离线地复现「python sycm_cli.py <子命令>」，
# 退出前把「sycm_cli 加载了几份」的判定打到 stdout。
#
# 用 exec 把 sycm_cli.py 跑进本进程的 __main__ 命名空间，而不是 runpy.run_path——
# run_path 会临时替换再还原 sys.modules["__main__"]，还原后就看不出真实身份关系了；
# exec 进 -c 进程自己的 globals 才和 `python sycm_cli.py` 的模块布局一致。
CHILD = r'''
import sys, types, platform

SKILL = sys.argv[1]
sys.path.insert(0, SKILL)

# Windows 分支会走 CDP 取 cookie，这里统一按 macOS 分支跑，保证跨平台一致
platform.system = lambda: "Darwin"

RISK_PAYLOAD = {"code": 0, "message": "滑块", "data": {}}


class _Resp:
    status_code = 200
    text = '{"code":0,"message":"滑块","data":{}}'

    def json(self):
        return RISK_PAYLOAD


class _RequestException(Exception):
    pass


req = types.ModuleType("curl_cffi.requests")
req.get = lambda *a, **k: _Resp()
req.post = lambda *a, **k: _Resp()
req.exceptions = types.SimpleNamespace(RequestException=_RequestException)
cc = types.ModuleType("curl_cffi")
cc.requests = req
sys.modules["curl_cffi"] = cc
sys.modules["curl_cffi.requests"] = req


class _Cookie:
    def __init__(self, name, value):
        self.name, self.value, self.domain = name, value, ".taobao.com"


bc3 = types.ModuleType("browser_cookie3")
bc3.chrome = lambda **k: [_Cookie("_tb_token_", "tok"), _Cookie("cookie2", "c2")]
sys.modules["browser_cookie3"] = bc3

SCRIPT = SKILL + "/sycm_cli.py"
sys.argv = ["sycm_cli.py"] + sys.argv[2:]
__file__ = SCRIPT
code = 0
try:
    exec(compile(open(SCRIPT, encoding="utf-8").read(), SCRIPT, "exec"), globals())
except SystemExit as e:
    code = e.code if isinstance(e.code, int) else 1

item = sys.modules.get("sycm_item")
main_mod = sys.modules["__main__"]
same_module = sys.modules.get("sycm_cli") is main_mod
# sycm_item 没有再导出 RiskTriggered，只能顺着它绑定的 _api_get 回看它实际用的那份
item_risk = item._api_get.__globals__.get("RiskTriggered") if item else None
same_class = item_risk is getattr(main_mod, "RiskTriggered", None)
print("SINGLE_COPY=%s SAME_RISK_CLASS=%s" % (same_module, same_class))
sys.exit(code)
'''


def _run_as_script(*cli_args):
    return subprocess.run(  # nosec B603 — 固定解释器 + 内联脚本，无 shell
        [sys.executable, "-c", CHILD, str(SKILL_DIR), *cli_args],
        capture_output=True, text=True, timeout=60,
    )


def test_risk_from_item_module_exits_with_code_2():
    """商品命令（实现在 sycm_item 里）触发风控时，进程必须以退出码 2 结束。

    修复前：sycm_item 抛的是第二份 sycm_cli 的 RiskTriggered，main() 捕不到，
    掉进 RuntimeError 分支 → 退出码 1、打印 "✗ …" 而不是风险信号横幅。
    """
    proc = _run_as_script("item-sku-list", "--item-id", "123456789")
    assert proc.returncode == 2, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "风险信号触发" in proc.stderr
    assert "✗" not in proc.stderr


def test_risk_from_main_module_exits_with_code_2():
    """对照组：主模块自己的命令本来就走对分支，修复不应破坏它。"""
    proc = _run_as_script("sale-shop-list", "--date", "2026-08-04")
    assert proc.returncode == 2, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "风险信号触发" in proc.stderr


def test_script_run_loads_sycm_cli_only_once():
    """脚本方式运行时 sycm_cli 只能有一份，否则跨模块的类身份/全局计数都会分裂。"""
    proc = _run_as_script("item-sku-list", "--item-id", "123456789")
    assert "SINGLE_COPY=True SAME_RISK_CLASS=True" in proc.stdout, proc.stdout
