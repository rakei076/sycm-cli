# 店铺数据工具 · 作者 Rakel · https://rakel.top · MIT 协议
"""浏览器插件桥。

为什么要有它：Windows 上的 Chrome 把 cookie 加密了，别的程序读不到；所以 Windows 上只能走插件。
所以改成：装一个只读的浏览器插件，让它在用户日常的 Chrome 里、通过已登录的平台页面去取数，再交给命令行。

通信方式：命令行临时开一个只监听 127.0.0.1 的小服务，插件来「拉任务、交结果」。
安全：
- 只监听本机；
- 只接受带插件自己 Origin（chrome-extension://<插件 ID>）的请求，普通网页伪造不了这个来源；
- 只允许平台声明的接口地址前缀（Platform.hosts）的 GET，和逐个登记的只读 POST（Platform.bridge_posts），其余一律拒绝（插件那边也各拦一遍）；
- 写操作永不走插件（BridgeSession.read_only）。
"""
from __future__ import annotations

import json
import json as _json   # BridgeSession.post 的参数名叫 json（和 curl_cffi 一致），会遮住模块名
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

from .errors import AccountChanged, LoginExpired, PluginChanged, Redirected
from urllib.parse import parse_qs, urlencode, urlsplit

from .platform import Platform

DEFAULT_PORT_RANGE = (47831, 47840)
# 一个插件服务所有平台，所以插件 ID 只在这里登记一次。DEV_EXTENSION_ID = 随交付包发的 extension/unpacked（带固定公钥）；
# STORE_EXTENSION_ID = Chrome 网上应用店分配的（从商店安装的都是这个）。临时加 ID：环境变量 <PREFIX>_EXTENSION_IDS（逗号分隔）。
DEV_EXTENSION_ID = "gifdenhgccikkfbodclkdbohicghfhco"
STORE_EXTENSION_ID = "ecahndljpkaakkjofejgcjnikikcemni"
EXTENSION_IDS = frozenset({DEV_EXTENSION_ID, STORE_EXTENSION_ID})
# 命令行要求的最低插件版本。插件从 0.4.0 起每次连命令行都报自己的版本（/hello、/next 的 v 参数）；不报的就是更旧的。
# 0.8.0 起每次交结果都报当时登录的账号（防串号要靠它）。
MIN_EXTENSION_VERSION = "0.8.0"


def min_version(plat: Platform) -> str:
    """这个平台要求的最低插件版本：底座默认要求和平台自己的要求取较高者。"""
    own = plat.min_extension
    return own if own and version_tuple(own) > version_tuple(MIN_EXTENSION_VERSION) else MIN_EXTENSION_VERSION


def version_tuple(v: str | None) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in (v or "").split("."))
    except ValueError:
        return ()


def port_range(plat: Platform) -> tuple[int, int]:
    """测试时用 <PREFIX>_BRIDGE_PORT 指定专属端口，避免和日常 Chrome 里的插件抢任务。"""
    p = plat.env("BRIDGE_PORT")
    return (int(p), int(p)) if p else DEFAULT_PORT_RANGE


def form_body(data: dict) -> str:
    """POST 的表单写法：字符串、数字原样，布尔写 true/false，列表和对象写成 JSON 字符串（网关按 JSON 解析这些字段）。"""
    def one(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (list, dict)):
            return _json.dumps(v, ensure_ascii=False, separators=(",", ":"))
        return "" if v is None else str(v)
    return urlencode({k: one(v) for k, v in (data or {}).items()})


class JobBox:
    """等插件来领的任务。带 to 的只给那个插件实例；不带的谁先来谁拿。"""

    def __init__(self):
        self._jobs: list[dict] = []
        self._cv = threading.Condition()

    def put(self, job: dict) -> None:
        with self._cv:
            self._jobs.append(job)
            self._cv.notify_all()

    def take(self, instance: str, timeout: float) -> dict | None:
        end = time.monotonic() + timeout
        with self._cv:
            while True:
                for i, job in enumerate(self._jobs):
                    if not job.get("to") or job["to"] == instance:
                        return self._jobs.pop(i)
                left = end - time.monotonic()
                if left <= 0:
                    return None
                self._cv.wait(left)


def allowed_prefixes(plat: Platform) -> tuple[str, ...]:
    return tuple(base.rstrip("/") + "/" for base in plat.hosts.values())


def _what(job: dict) -> str:
    """调试日志里一个任务的简称。"""
    if job.get("account"):
        return "账号 " + str(job["account"].get("op"))
    return str(job.get("url") or job.get("cookie"))[:80]


def _dbg(plat: Platform, msg: str) -> None:
    import sys, time as _t
    if plat.env("DEBUG"):
        print(f"[bridge {_t.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


SWITCH_HINT = ("可能有其他命令或用户在插件中切换了账号。请确保同一时间只读取一个账号的数据；如需读取指定账号，"
               "请使用 tb --account <账号名称> <平台> <命令>（MCP 中填写 run 的 account 参数），工具会在同一条命令中完成切换和读取。")


class BridgeError(RuntimeError):
    no_retry = True  # 插件超时/被拒，重试只会把等待翻倍；直接报错


class BridgeTimeout(BridgeError):
    pass


class BridgeRefused(BridgeError):
    pass


def allowed_ids(plat: Platform) -> set[str]:
    only = {x.strip() for x in (plat.env("ONLY_EXTENSION_IDS") or "").split(",") if x.strip()}
    if only:   # 测试用：只认指定的插件实例（避免日常 Chrome 里装的插件抢任务）
        return only
    extra = {x.strip() for x in (plat.env("EXTENSION_IDS") or "").split(",") if x.strip()}
    return set(EXTENSION_IDS) | extra


def _dev_build() -> str | None:
    """开发时：extension/dist/BUILD 里是最新构建号；交付包里没有这个文件，就不报。"""
    from pathlib import Path
    f = Path(__file__).resolve().parents[2] / "extension" / "dist" / "BUILD"
    try:
        return f.read_text().strip() or None
    except OSError:
        return None


def _lock_path(plat: Platform | None = None):
    """排队锁：整台电脑一把（插件只有一个，装了几份工具也要排同一个队）。
    测试给平台指定了专属端口（<PREFIX>_BRIDGE_PORT）时，不和日常命令抢插件，锁也按端口分开、放在自己的状态目录。"""
    from .paths import machine_root, state_root
    port = plat.env("BRIDGE_PORT") if plat is not None else None
    return state_root() / f"bridge-{port}.lock" if port else machine_root() / "bridge.lock"


class BridgeLock:
    """同一时间只让一个命令用浏览器插件。插件一次只服务一个本机服务，两个命令同时等插件时，后来的那个会一直连不上；
    所以后来的命令先排队，等前一个用完再开始。进程退出时系统自动释放锁，不会留下死锁。"""

    WAIT = 15 * 60

    def __init__(self, path=None):
        self.path = path or _lock_path()
        self._f = None

    def _try(self) -> bool:
        import os
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def acquire(self, wait: float | None = None) -> None:
        import sys, time
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(self.path, "a+")
        if self._try():
            return
        print("… 另一个取数命令正在用浏览器插件，排队等它结束后再开始", file=sys.stderr, flush=True)
        end = time.time() + (self.WAIT if wait is None else wait)
        while time.time() < end:
            time.sleep(0.5)
            if self._try():
                return
        self._f.close()
        self._f = None
        raise BridgeError(f"另一个取数命令占用浏览器插件超过 {int((self.WAIT if wait is None else wait) / 60)} 分钟。"
                          "等它跑完再试；如果没有别的命令在跑，关掉多余的终端或 AI 助手窗口后再试。")

    def release(self) -> None:
        import os
        if self._f is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self._f.seek(0)
                msvcrt.locking(self._f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._f.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self._f.close()
        self._f = None


class _Handler(BaseHTTPRequestHandler):
    server: "BridgeServer"

    def log_message(self, *args):  # 不往终端打日志
        pass

    def _origin_ok(self) -> bool:
        """预检（OPTIONS）：Origin 必须是允许的插件。
        真正的请求（GET/POST）：Chrome 对插件发的 GET 不带 Origin，所以要求带自定义头 X-Dmp-Bridge=<插件 ID>。
        自定义头会触发预检，普通网页要带上它必须先过预检，而预检只对插件 ID 放行，所以网页伪造不了。"""
        prefix = "chrome-extension://"
        origin = self.headers.get("Origin") or ""
        ids = allowed_ids(self.server.platform)
        if origin:
            return origin.startswith(prefix) and origin[len(prefix):] in ids
        return (self.headers.get("X-Dmp-Bridge") or "") in ids

    def _send(self, code: int, body: str = "", ctype: str = "application/json; charset=utf-8") -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        origin = self.headers.get("Origin")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Private-Network", "true")
        if data:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def do_OPTIONS(self):
        if not self._origin_ok():
            return self._send(403)
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin"))
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Access-Control-Allow-Headers", "X-Dmp-Bridge, Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()

    def do_GET(self):
        if not self._origin_ok():
            return self._send(403, '{"error":"forbidden"}')
        url = urlsplit(self.path)
        version = parse_qs(url.query).get("v", [""])[0]
        inst = parse_qs(url.query).get("i", [""])[0]
        if version:   # 插件报的自己的版本
            self.server.extension_version = version
            if inst:
                self.server.versions[inst] = version
        self.server.saw_instance(inst)   # 插件 0.8.0 起报自己的实例编号
        if url.path == "/hello":
            self.server.extension_seen.set()
            self.server.requeue_taken(inst)   # 插件重连（多半是被 Chrome 休眠后重启）：它领走没交结果的任务再派一次
            hello = {"app": self.server.platform.hello_app, "version": 1}
            build = _dev_build()
            if build:
                hello["extension_build"] = build
            return self._send(200, json.dumps(hello))
        if url.path == "/next":
            self.server.extension_seen.set()
            wait = min(max(float(parse_qs(url.query).get("wait", ["20"])[0]), 0.0), 25.0)
            job = self.server.jobs.take(inst, wait)
            if job is None:
                return self._send(204)
            self.server.taken[job["id"]] = (job, inst)
            _dbg(self.server.platform, f"插件取走任务 {_what(job)}")
            return self._send(200, json.dumps(job))
        self._send(404)

    def do_POST(self):
        if not self._origin_ok():
            return self._send(403, '{"error":"forbidden"}')
        if urlsplit(self.path).path != "/result":
            return self._send(404)
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8", "replace")
        try:
            msg = json.loads(raw)
            job_id = msg["id"]
        except (ValueError, KeyError, TypeError):
            return self._send(400)
        self.server.taken.pop(job_id, None)
        waiter = self.server.pending.get(job_id)
        if waiter is None:
            return self._send(404)
        _dbg(self.server.platform, f"收到插件结果 status={msg.get('status')} error={str(msg.get('error'))[:120]} 内容长度={len(msg.get('text') or '')}")
        waiter["result"] = msg
        if msg.get("browser"):
            self.server.browser = msg["browser"]
        waiter["event"].set()
        self._send(200, "{}")


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, platform: Platform):
        self.platform = platform
        self.jobs = JobBox()
        self.bound: str | None = None    # 选定的插件实例（几个浏览器都装了插件时，任务只派给它；见 browsers.choose）
        self.pending: dict[str, dict] = {}
        self.taken: dict[str, tuple[dict, str]] = {}   # 插件领走、还没交结果的任务：编号 → (任务, 领走的插件实例)
        self.extension_seen = threading.Event()
        self.browser: str | None = None   # 插件回报的浏览器信息（第一次收到结果时记录），用来告诉用户是哪个浏览器在取数
        self.extension_version: str | None = None   # 插件报的版本；旧插件不报，保持 None
        self.versions: dict[str, str] = {}           # 每个插件实例报的版本（几个浏览器都装了插件时版本可能不同）
        self.instances: list[str] = []   # 来连过的插件实例编号（一台电脑上几个浏览器 / Chrome 资料都装了插件时不止一个）
        last: Exception | None = None
        lo, hi = port_range(platform)
        for port in range(lo, hi + 1):
            try:
                super().__init__(("127.0.0.1", port), _Handler)
                break
            except OSError as ex:
                last = ex
        else:
            import errno
            if getattr(last, "errno", None) in (errno.EPERM, errno.EACCES):
                # 沙箱（如 Codex 默认权限）不让开本机端口：这不是端口被占，别让人去查谁占了端口
                raise BridgeError("当前环境不允许在本机开端口，浏览器插件没法连进来。多半是命令在 AI 助手（如 Codex）的沙箱里运行。"
                                  "请改用 MCP：在你自己打开的终端里运行一次 mcp install（例如 scripts/<工具>.sh mcp install，Windows 用 scripts\\<工具>.cmd mcp install），完全退出并重开 Codex，之后让它通过 MCP 取数；也可以直接在你自己打开的终端里运行这条命令。"
                                  f"（{last}）")
            raise BridgeError(f"本机 {lo}–{hi} 端口都被占用了：{last}")
        self.port = self.server_address[1]
        self._thread: threading.Thread | None = None

    def saw_instance(self, inst: str) -> None:
        """记下来连的插件实例（一台电脑上几个浏览器 / Chrome 用户资料都装了插件时不止一个；选哪个见 browsers.choose）。"""
        if not inst or inst in self.instances:
            return
        self.instances.append(inst)
        from . import runlog
        runlog.event("instance", instance=inst, count=len(self.instances))
        if len(self.instances) == 2:
            from . import browsers
            browsers.mark_multi()

    def requeue_taken(self, instance: str = "") -> None:
        """只重派这个插件自己领走、还没交结果的任务：别的插件来连，不能把正在别处执行的任务再派一遍。"""
        for job_id, (job, by) in list(self.taken.items()):
            if by != instance:
                continue
            if self.taken.pop(job_id, None) is not None and job_id in self.pending:
                _dbg(self.platform, f"插件重连，重新派发 {_what(job)}")
                self.jobs.put(job)

    def version_of(self, instance: str | None) -> str | None:
        """这个插件报的版本；没指定插件（只有一个、或旧插件不报编号）时用最后报的那个。"""
        return self.versions.get(instance or "") or self.extension_version

    def start(self) -> None:
        self._lock = BridgeLock(_lock_path(self.platform))
        self._lock.acquire()
        self._thread = threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.shutdown()
        self.server_close()
        lock = getattr(self, "_lock", None)
        if lock is not None:
            lock.release()
            self._lock = None

    SLOW_NOTICE_AFTER = 8.0

    def submit(self, job: dict, timeout: float, to: str | None = None) -> dict:
        """派发一个任务（取数 {"url"} 或读 cookie {"cookie"}）并等结果。launch 告诉插件从哪个平台页面发。
        to：只派给这个插件实例；不给就派给选定的那个（bound），都没有就谁先来谁拿。"""
        job_id = uuid.uuid4().hex
        waiter = {"event": threading.Event(), "result": None}
        self.pending[job_id] = waiter
        _dbg(self.platform, f"派发任务 {_what(job)}")
        target = to or self.bound
        self.jobs.put({"id": job_id, "launch": self.platform.launch_url, **job, **({"to": target} if target else {})})
        try:
            first = min(self.SLOW_NOTICE_AFTER, timeout)
            if not waiter["event"].wait(first):
                import sys
                print(f"… {self.platform.display}响应比较慢，还在等浏览器返回（网络慢时一个请求可能要十几秒）", file=sys.stderr)
                if not waiter["event"].wait(max(0.0, timeout - first)):
                    raise BridgeTimeout(f"浏览器插件在 {int(timeout)} 秒内没有返回结果。请确认 Chrome 开着、网络能打开{self.platform.display}。")
            return waiter["result"]
        finally:
            self.pending.pop(job_id, None)


def _nick(who: dict | None) -> str:
    """「昵称（账号编号）」：昵称可能一样（同一家店的子账号），带上编号才分得清。"""
    nick, uid = (who or {}).get("nick") or "", (who or {}).get("uid") or ""
    if not uid:
        return "未登录"
    return f"{nick}（{uid}）" if nick else uid


def _meta(res: dict) -> dict:
    """插件随结果报的现场（写进运行日志）：当时登录的账号、发射台标签页、插件里的耗时和重试次数。"""
    names = {"who": "who", "whoAfter": "whoAfter", "tab": "tab", "ms": "plugin_ms", "attempts": "plugin_attempts",
             "instance": "instance"}
    return {mine: res[theirs] for theirs, mine in names.items() if theirs in res}


class BridgeSession:
    """和 curl_cffi Session 同样的 .get / .post 接口，请求交给浏览器插件去发。
    请求头由浏览器按页面自己的规矩带（Origin、Referer、cookie），命令行传来的头不转交。

    一条命令只认一个账号：插件每次交结果都报请求前后浏览器里登录的账号（who / whoAfter）。
    认定的账号 = --account 换好的那个，没指定就是第一次取数时登录的那个；之后哪次不一样，整条命令报错作废，
    免得别的命令或有人在插件里切换账号时，把另一个账号的数据混进来。"""

    read_only = True   # 插件只读：Client 据此拒绝一切写操作

    def __init__(self, server: BridgeServer):
        self.server = server
        self.account: dict | None = None   # {"uid", "nick"}：这条命令认定的账号
        self.instance: str | None = None   # 这条命令认定的插件实例（第一个交结果的那个）

    def _check_instance(self, res: dict) -> None:
        inst = res.get("instance") or ""
        if self.instance is None:
            self.instance = inst
        elif inst != self.instance:
            raise PluginChanged(f"本次命令的请求由两个不同的取数桥插件处理（编号 {self.instance}、{inst}）。它们位于不同的浏览器或 "
                                "Chrome 用户资料中，登录的可能是不同的店铺，本次数据已作废。", stage="插件检查",
                                hint="请只在一个浏览器中启用取数桥插件：在其他浏览器或 Chrome 用户资料中打开 chrome://extensions，关闭该插件后重新运行。")

    def _check_who(self, res: dict) -> None:
        self._check_instance(res)
        who, after = res.get("who") or {}, res.get("whoAfter")
        if after is not None and (after or {}).get("uid") != who.get("uid"):
            raise AccountChanged(f"读取过程中，浏览器的登录账号发生了变化（请求前为「{_nick(who)}」，请求后为「{_nick(after)}」）。本次数据已作废。",
                                 stage="账号检查", hint=SWITCH_HINT)
        if self.account is None:
            self.account = {"uid": who.get("uid") or "", "nick": who.get("nick") or ""}
            return
        if (who.get("uid") or "") != self.account["uid"]:
            raise AccountChanged(f"读取过程中，浏览器的登录账号发生了变化：本次命令使用的账号为「{_nick(self.account)}」，"
                                 f"该请求发出时登录的是「{_nick(who)}」。本次数据已作废。", stage="账号检查", hint=SWITCH_HINT)

    def _url(self, url: str, params: dict | None) -> str:
        if params:
            url = url + ("&" if "?" in url else "?") + urlencode(params)
        if not url.startswith(allowed_prefixes(self.server.platform)):
            raise BridgeRefused(f"插件桥只放行{self.server.platform.display}的接口地址，拒绝：{url[:80]}")
        return url

    def _fail(self, res: dict):
        """插件回了错误。打不开平台页面（被带去登录页、错误页）是登录或权限问题，按登录失效报；其余是插件的问题。"""
        if res.get("notLanded"):   # 插件 0.5.0 起
            display = self.server.platform.display
            raise LoginExpired(str(res["error"]), stage="打开平台页面",
                               hint=f"在这个 Chrome 里打开{display}看一下：要求登录就登录一次；已经登录了还进不去，"
                                    f"多半是这个账号没有{display}的权限（子账号要请主账号开通）。")
        raise BridgeError(str(res["error"]))

    def _reply(self, res: dict):
        if res.get("error"):
            self._fail(res)
        self._check_who(res)
        if res.get("redirectedAway"):   # 插件 0.5.0 起：跟跳转失败时确认过是被平台转走了
            display = self.server.platform.display
            raise Redirected(f"{display}没有回数据，而是把请求转去了别的页面（多半是「访客太多，排队接待中」的排队页，也可能是登录页）。",
                             stage="平台返回", hint=f"在浏览器里打开{display}看一下：显示排队就过一会儿再试；要求登录就重新登录。")
        return SimpleNamespace(status_code=int(res.get("status") or 0), text=res.get("text") or "",
                               url=res.get("landed") or "", meta=_meta(res))

    def get(self, url: str, params: dict | None = None, timeout: float | None = None, headers: dict | None = None):
        return self._reply(self.server.submit({"url": self._url(url, params)}, timeout or 60))

    def post(self, url: str, params: dict | None = None, json: object = None, timeout: float | None = None,
             headers: dict | None = None):
        """只放行平台登记的只读 POST 接口（Platform.bridge_posts）。body 按 JSON 发。"""
        url = self._url(url, params)
        plat = self.server.platform
        if not plat.bridge_post_allowed(urlsplit(url).path):
            raise BridgeRefused(f"插件桥只放行{plat.display}登记过的只读查询接口，拒绝：{urlsplit(url).path}")
        data = json if json is not None else {}
        if url.startswith(plat.bridge_form_hosts) and plat.bridge_form_hosts:
            return self._reply(self.server.submit({"url": url, "method": "POST", "body": form_body(data), "form": True}, timeout or 60))
        body = _json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return self._reply(self.server.submit({"url": url, "method": "POST", "body": body}, timeout or 60))

    def cookie(self, name: str) -> str | None:
        """让浏览器读一个 cookie（只放行平台声明的名字，如 mtop 令牌）；没有返回 None。"""
        if name not in self.server.platform.readable_cookies:
            raise BridgeRefused(f"插件桥不读这个 cookie：{name}")
        res = self.server.submit({"cookie": name}, 30)
        if res.get("error"):
            self._fail(res)
        self._check_who(res)
        return res.get("value") or None
