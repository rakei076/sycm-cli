"""生意参谋（sycm.taobao.com）平台描述。全部只读 GET。"""
import re

from ...core.platform import Platform
from . import session

SYCM = Platform(
    name="sycm",
    display="生意参谋",
    hosts={
        "api": "https://sycm.taobao.com/csp/api",   # 旧 CSP 接口
        "root": "https://sycm.taobao.com",          # /cc /flow /mc /portal ... 各接口族
    },
    login_page="https://sycm.taobao.com/",
    launch_url="https://sycm.taobao.com/robots.txt",
    login_cookies=("cookie2", "unb"),
    cookie_domains=("taobao.com", "sycm.taobao.com"),   # 目标站点的同名 cookie 优先
    referer="https://sycm.taobao.com/qos/service/frame/performance/detail/new",
    expired_hints=(),
    # 只读防护：路径里出现这些「动词段」一律拒绝（按 / 和 . 切段）
    write_re=re.compile(r"(^|[/.])(add|create|update|delete|remove|save|submit|cancel|set|edit|upload|apply|bind|unbind)([/.]|$)", re.I),
    env_prefix="SYCM",
    risk_words=("滑块", "验证码", "操作过于频繁", "请重新登录", "异常请求", "风控"),
    risk_exempt=("618",),    # 618 大促文案里会带风控字样
    delay=(1.8, 3.5),
    warn_after=200,
    readable_cookies=("_tb_token_",),   # 接口参数里要带的防 CSRF 令牌（命令行自己拿不到时向浏览器要）
    check_payload=session.check_payload,
)
