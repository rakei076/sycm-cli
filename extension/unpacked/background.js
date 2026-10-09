// taobao-cli 取数桥（后台）
// 一个插件服务所有本机工具：tb（生意参谋 / 万相台 / 千牛 / 达摩盘 / 1688）、taobao-voc。
// 工作方式：本机的命令行临时开一个只监听 127.0.0.1 的小服务；这里去「拉任务」，
// 在对应平台的已登录页面里用页面自己的身份发只读请求，再把结果交回去。
// 安全：只放行 SITES 里登记的接口；GET 按地址前缀 + 写操作词拦截，POST 只放行逐个列出的只读查询接口（精确路径）；
//       只读各平台登记的 cookie；结果只交给本机的命令行，不发往任何别处。

const PORTS = [47831, 47832, 47833, 47834, 47835, 47836, 47837, 47838, 47839, 47840];

// ---- 放行规则开始（tests/test_extension_release.py 会原样取出这一段运行，改动时保持自包含）----
// MTOP 签名令牌和防 CSRF 参数：命令行要用它们算签名 / 带进参数。登录 cookie（cookie2 等）一概不读。
const TOKENS = ["_m_h5_tk", "_m_h5_tk_enc", "_tb_token_"];
// 每个平台一项：键 = 发请求用的「发射台」页面（平台域名下极轻的同域小文档）。
//   ALLOWED  允许的 GET 地址；WRITE = 名字像写操作的路径（拒绝）；SERVICES = 只认这些 serviceId（1688）
//   POSTS    允许的 POST 接口：字符串 = 精确路径，正则 = 只为带编号的路径（域名是发射台本身或 ALLOWED 里的接口域名）；没有这一项的平台不放行任何 POST
//   COOKIES  允许读的 cookie；HTTPONLY = 其中页面脚本读不到、要用 chrome.cookies 读的那几个
const SITES = {
  "https://dmp.taobao.com/robots.txt": {
    ALLOWED: [/^https:\/\/dmp\.taobao\.com\/api_2\//, /^https:\/\/dmp\.advgateway\.taobao\.com\/api\//],
    WRITE: /(^|\/)(add|create|update|delete|del|remove|save|submit|bind|unbind|cancel|set|apply|edit|upload|push|send|sync|copy|move|rename|batch|start|stop|pay|recharge|buy|generate|subscription)(\/|$|\?)/i,
    // 达摩盘人群画像：这几个接口用 POST 传查询条件，但只读（网页「画像透视」用的就是它们）
    POSTS: ["/api_2/analysis/insight/tag/list", "/api_2/analysis/insight/feature", "/api_2/analysis/insight/coverage",
            /^\/api_2\/analysis\/tag\/\d+$/,
            // 竞争商品分析：广告网关上的 6 个只读查询
            "/api/competition/analysis/base/control/ratio", "/api/competition/analysis/base/shop/indicator",
            "/api/competition/analysis/base/indicator", "/api/competition/analysis/flow/paid_free/structural",
            "/api/competition/analysis/flow/investor/structural", "/api/competition/analysis/flow/indicator",
            "/api/dmp/insight/tag/chart"],   // 客群分析：一个人群在一个画像标签上的分布
    COOKIES: TOKENS,
  },
  "https://myseller.taobao.com/robots.txt": {
    ALLOWED: [/^https:\/\/h5api\.m\.taobao\.com\/h5\//, /^https:\/\/ascp-plan-control-tower-web\.dchain-api-proxy\.taobao\.com\/data\/lg\//],
    WRITE: /(update|create|delete|modify|save|add|remove|edit|submit|send|post|set|operate|publish|cancel|confirm|pay|refund)/i,
    // 退款管理的读接口：名字带 refund 会被上面误拦，逐个放行（和命令行 Platform.read_allow 一致）；同意/拒绝退款等写接口不在这里
    READS: [
      "/h5/mtop.alibaba.refundface2.disputeservice.qianniu.pc.statistic/1.0/",
      "/h5/mtop.alibaba.refundface2.disputeservice.qianniu.pc.indecator/1.0/",
      "/h5/mtop.alibaba.refundface2.disputeservice.qianniu.pc.disputelistv2/1.0/",
    ],
    COOKIES: TOKENS,
  },
  "https://sycm.taobao.com/robots.txt": {
    ALLOWED: [/^https:\/\/sycm\.taobao\.com\//],
    WRITE: /(^|[/.])(add|create|update|delete|remove|save|submit|cancel|set|edit|upload|apply|bind|unbind)([/.]|$)/i,
    COOKIES: TOKENS,
  },
  // 万相台：读取接口全是 POST。只放行下面这些查询接口；关停广告（/adgroup/updatePart.json）等写接口不在清单里，插件永远发不出去。
  "https://one.alimama.com/index.html": {
    POSTS: [
      "/member/checkAccess.json", "/account/checkRealBalance.json", "/activity/getActivityList.json",
      "/report/query.json", "/report/chargeSum.json", "/report/campaign/findPage.json", "/report/adgroup/findPage.json",
      "/campaign/horizontal/findPage.json", "/adgroup/horizontal/findPage.json",
    ],
    REFERRER: "https://one.alimama.com/index.html",
    XSRF: "XSRF-TOKEN",   // 页面自己的请求会把这个 cookie 放进 X-XSRF-TOKEN 头，这里照做
    COOKIES: [],
  },
  // 1688 卖家工作台：订单走同一个 MTOP 接口（dataline.service），读写只能靠参数里的 serviceId 区分，所以那一个接口还要 serviceId 白名单；
  // 其余是逐个登记的只读接口（商品列表 / 流量 / 诊断、订单看板、物流、星级、询价、账单），名字以外的一概不放。
  "https://air.1688.com/robots.txt": {
    ALLOWED: [/^https:\/\/h5api\.m\.1688\.com\/h5\/(mtop\.1688\.trading\.dataline\.service|mtop\.1688\.offermanage\.offerlistquery|mtop\.1688\.offermanagedetailqueryservice\.getflowdatas|mtop\.alibaba\.cbu\.diag\.query\.item\.task|mtop\.1688\.offermanage\.growth\.queryaitasks|mtop\.alibaba\.cbu\.diag\.health\.overview|mtop\.alibaba\.cbu\.diag\.health\.effect\.data|mtop\.alibaba\.cbu\.diag\.health\.suggestion\.cards|mtop\.1688\.diagnosis\.offer\.querytaskinfolist|mtop\.cbu\.global\.fulfillment\.checkoutorder\.queryordercount|mtop\.1688\.com\.cnortools\.businesswarnservice\.kanban|mtop\.1688\.orderlogisticstagreadservice\.batchgettags|mtop\.cbu\.logistics\.operationworkplatform\.querydata|mtop\.1688\.offical\.lgt\.queryselleruserinfo|mtop\.alibaba\.cbu\.supplychain\.star\.querystarinfo|mtop\.1688\.industry\.app\.quotation\.seller\.list\.query|mtop\.1688\.shellcenter\.settle\.bill\.queryinitconfig|mtop\.1688\.shellcenter\.settle\.bill\.querysellerarrearsdetails)\/1\.0\//],
    WRITE: /(update|create|delete|remove|modify|save|submit|cancel|operate|refund|close|pay)/i,
    SERVICE_API: /\/mtop\.1688\.trading\.dataline\.service\//,
    SERVICES: ["OrderListDataLineService.sellerOrderList", "OrderListDataLineService.sellerOrderStat"],
    COOKIES: TOKENS,
  },
  // 1688 生意参谋：全是 GET，靠登录 cookie，不读任何 cookie。只放行 /ms/ 下的数据接口，名字像写操作的拒绝。
  "https://sycm.1688.com/ms/common/commDate.json": {
    ALLOWED: [/^https:\/\/sycm\.1688\.com\/ms\//],
    WRITE: /(^|[/.])(add|create|update|delete|remove|save|submit|cancel|set|edit|upload|apply|bind|unbind|follow|unfollow|subscribe|order|buy|pay|send|modify|operate)([/.]|$)/i,
    COOKIES: [],
  },
  // taobao-voc（买家账号看竞品）：只放行搜索、评价、问大家三个接口。
  // unb（账号 ID）用来判断登录的是不是买家号、问大家接口要带；它是 HttpOnly，只能用 chrome.cookies 读，且只在这个平台读。
  "https://item.taobao.com/robots.txt": {
    ALLOWED: [/^https:\/\/h5api\.m\.taobao\.com\/h5\/(mtop\.relationrecommend\.wirelessrecommend\.recommend|mtop\.taobao\.rate\.detaillist\.get|mtop\.taobao\.wdj\.list\.merge\.search)\/[0-9.]+\//],
    WRITE: /(update|create|delete|modify|save|add|remove|edit|submit|send|post|set|operate|publish|cancel|confirm|pay|refund)/i,
    COOKIES: ["_m_h5_tk", "_m_h5_tk_enc", "tracknick", "unb"],
    HTTPONLY: ["unb"],
  },
};

function allowed(job) {
  const site = SITES[job.launch];
  if (!site) return false;
  if (job.cookie) return site.COOKIES.includes(job.cookie);
  let u;
  try { u = new URL(job.url); } catch (_) { return false; }
  if (job.method === "POST") {
    // 域名只能是发射台本身，或这个平台登记过的接口域名（如达摩盘的广告网关）；路径逐个登记
    const host = u.origin === new URL(job.launch).origin || (site.ALLOWED || []).some((re) => re.test(job.url));
    return !!site.POSTS && host && typeof job.body === "string" && job.body.length <= 200000
      && site.POSTS.some((p) => (typeof p === "string" ? p === u.pathname : p.test(u.pathname)));
  }
  if (job.method && job.method !== "GET") return false;
  if (!site.ALLOWED || !site.ALLOWED.some((re) => re.test(job.url))) return false;
  if (site.WRITE.test(u.pathname) && !(site.READS && site.READS.includes(u.pathname))) return false;
  if (site.SERVICES && (!site.SERVICE_API || site.SERVICE_API.test(u.pathname))) {
    try { return site.SERVICES.includes(JSON.parse(u.searchParams.get("data")).serviceId); }
    catch (_) { return false; }
  }
  return true;
}
// ---- 放行规则结束 ----

const DEV_AUTO_RELOAD = false;   // build.py 只在开发版里改成 true
const BUILD = "b2028f2e96e2";        // build.py 写入构建号
const HEADERS = { "X-Dmp-Bridge": chrome.runtime.id };  // 身份头：服务端只认允许的插件 ID（同时让浏览器先发预检）
// 每次连命令行都报上自己的版本（放在网址参数里，不加新的请求头，免得旧命令行的预检不认）
const VERSION = chrome.runtime.getManifest().version;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let base = null;       // 当前连上的本机服务，例如 http://127.0.0.1:47831
let running = false;   // 拉任务的循环是否在跑
let idleSince = 0;     // 开始「没有命令行在等」的时间
const state = { connected: false, app: "", lastJob: 0, jobs: 0, lastError: "" };

const log = (...a) => console.log("[taobao-cli]", ...a);

// 用户可以在弹窗里关掉某些工具（例如买家号和卖家号分在两个 Chrome 资料里时，各自只服务自己那一边）
async function disabledApps() {
  try { return (await chrome.storage.local.get("off")).off || []; } catch (_) { return []; }
}

async function findBridge() {
  const off = await disabledApps();
  for (const p of PORTS) {
    try {
      const r = await fetch(`http://127.0.0.1:${p}/hello?v=${VERSION}`, { headers: HEADERS, signal: AbortSignal.timeout(800) });
      if (r.ok) {
        const hello = await r.json();
        if (/^[a-z]+-cli$/.test(hello.app || "")) {
          if (off.includes(hello.app)) { log("端口", p, "是", hello.app, "，已在弹窗里关掉，不服务"); continue; }
          if (DEV_AUTO_RELOAD && hello.extension_build && hello.extension_build !== BUILD) { log("开发版：发现新构建，重载自己"); chrome.runtime.reload(); return null; }
          log("找到本机服务，端口", p, hello.app);
          state.app = hello.app;
          return `http://127.0.0.1:${p}`;
        }
      }
      log("端口", p, "有服务但被拒绝或不是本机取数工具，状态", r.status);
    } catch (_) { /* 这个端口没有服务 */ }
  }
  return null;
}

// 取数的「发射台」：平台域名下的一个页面，请求从这里发出（身份、cookie 和用户在网页里点的完全一样）。
// 平台整个页面很重、网络慢时要加载很久，所以不依赖用户已经打开的那个页面，而是自己开一个极轻的同域小文档
// （robots.txt，只有几十字节），用完自动关掉。
// 有的平台（万相台）打开任何页面都会先经过淘宝统一登录中转，回来时网址多一个参数，所以按前缀找、按域名验。
let helperTimer = null;
let inFlight = 0;   // 正在进行的请求数：有请求在跑时，发射台绝不能被关掉

class NotLanded extends Error {}
class PageNotOpened extends Error {}   // 辅助页面没打开（没加载完、空白页、错误页）：可能是一时的，重试一次

// 淘宝系的统一登录页：停在这些地址上才说明没登录
const LOGIN_HOSTS = ["login.taobao.com", "login.tmall.com", "login.1688.com", "login.m.taobao.com",
  "havanalogin.taobao.com", "passport.alibaba.com", "passport.taobao.com"];

function hostOf(url) {
  try { return new URL(url).host; } catch (_) { return ""; }
}

function isLoginPage(url) {
  try {
    const u = new URL(url);
    return LOGIN_HOSTS.includes(u.host) || /login/i.test(u.pathname);
  } catch (_) { return false; }
}

// 打开页面途中经过登录中转时，Chrome 可能把整个标签页换成新的（编号变了）：记下来，跟着换
const replacedBy = {};
chrome.tabs.onReplaced.addListener((added, removed) => { replacedBy[removed] = added; });

const helpers = {};   // 发射台 -> 自己开的标签页 ID（登录中转后网址可能变了，按地址找不到，所以记下来）

async function launchTab(launchUrl) {
  const origin = new URL(launchUrl).origin;
  if (helpers[launchUrl]) {
    try {
      const t = await chrome.tabs.get(helpers[launchUrl]);
      if (!t.discarded && t.status === "complete" && t.url && t.url.startsWith(origin + "/")) return t;
    } catch (_) { /* 被用户关掉了 */ }
    delete helpers[launchUrl];
  }
  // 内存里的记录可能丢（Chrome 会回收空闲的 service worker）：按地址在所有标签页里找，能接管之前遗留的。
  const found = (await chrome.tabs.query({ url: launchUrl + "*" })).find((t) => !t.discarded && t.status === "complete");
  if (found) return found;
  let t;
  try {
    t = await chrome.tabs.create({ url: launchUrl, active: false });
  } catch (e) {
    // 有的浏览器（如 Codex 内置浏览器 Owl）不许插件开后台标签页：改开在前台
    log("后台标签页开不了，改在前台打开", String(e));
    t = await chrome.tabs.create({ url: launchUrl, active: true });
  }
  const tab = await waitLanded(t.id, origin);
  if (!tab || !tab.url || new URL(tab.url).origin !== origin) {
    try { await chrome.tabs.remove(tab ? tab.id : t.id); } catch (_) {}
    const where = tab && tab.url ? hostOf(tab.url) : "";
    // 只有真的停在登录页才算没登录；没加载完、空白页、错误页都可能是一时的，交给上层重试
    if (where && isLoginPage(tab.url)) {
      throw new NotLanded(`打开 ${origin} 时被带去了登录页（${where}）：这个浏览器里没有登录这个平台。`);
    }
    const blocked = where === "error.taobao.com" ? (new URL(tab.url).searchParams.get("error") || "未知原因") : "";
    const state = !tab ? "标签页不见了" : blocked ? `被淘宝拦到了错误页，原因：${blocked}` : where ? "停在了 " + where
      : tab.status === "complete" ? "25 秒内没有回到平台页面，多半停在淘宝登录页：在 Chrome 里打开它看看要不要登录" : "25 秒内没加载完";
    throw new PageNotOpened(`辅助页面 ${origin} 没有打开（${state}）`);
  }
  helpers[launchUrl] = tab.id;
  return tab;
}

// 等发射台加载完并停在平台自己的域名上（中途经过登录中转也算），最多 25 秒
// 停在别的网站上不动了（加载完 4 秒还没跳回来）就不再等：多半是登录页、错误页，不是登录中转。
// 插件没有读所有网址的权限，停在没登记的网站（如 login.taobao.com）时网址是空的：这种情况等满时限。
function waitLanded(tabId, origin, ms = 25000, settle = 4000) {
  return new Promise((resolve) => {
    const t0 = Date.now();
    let away = null;   // 加载完停在别处的那个网址，和从什么时候开始停着
    const tick = async () => {
      while (replacedBy[tabId]) tabId = replacedBy[tabId];
      let tab; try { tab = await chrome.tabs.get(tabId); } catch (_) {
        if (replacedBy[tabId]) return tick();
        await sleep(300);   // 替换事件可能晚一点到
        if (replacedBy[tabId]) return tick();
        return resolve(null);
      }
      const home = tab.url && tab.url.startsWith(origin + "/");
      if ((tab.status === "complete" && home) || Date.now() - t0 > ms) return resolve(tab);
      // 网址看不到（停在没登记的网站上，多半是淘宝登录中转）：不提前放弃，等满时限让它跳回来
      if (tab.status === "complete" && !home && tab.url) {
        if (!away || away.url !== tab.url) away = { url: tab.url, since: Date.now() };
        else if (Date.now() - away.since > settle) return resolve(tab);
      } else away = null;
      setTimeout(tick, 200);
    };
    tick();
  });
}

function scheduleClose() {   // 空闲 60 秒后关掉发射台，不在用户浏览器里留下多余标签页
  clearTimeout(helperTimer);
  helperTimer = setTimeout(async () => {
    if (inFlight > 0) return scheduleClose();
    for (const launchUrl of Object.keys(SITES)) {
      const ids = new Set((await chrome.tabs.query({ url: launchUrl + "*" })).map((t) => t.id));
      if (helpers[launchUrl]) ids.add(helpers[launchUrl]);
      delete helpers[launchUrl];
      for (const id of ids) { try { await chrome.tabs.remove(id); } catch (_) {} }
    }
  }, 60000);
}

async function runInPage(job) {
  inFlight += 1;
  clearTimeout(helperTimer);
  try { return await runInPageInner(job); }
  finally { inFlight -= 1; scheduleClose(); }
}

// 在发射台页面里执行的函数（运行在页面里，不能引用外面的变量）
function pageReadCookie(name) {
  const hit = document.cookie.split("; ").find((c) => c.startsWith(name + "="));
  return { value: hit ? hit.slice(name.length + 1) : "" };
}

async function pageFetch(u, method, body, referrer, xsrf) {
  try {
    const init = { credentials: "include" };
    if (method === "POST") {
      const headers = { "Content-Type": "application/json", "Accept": "application/json, text/plain, */*", "X-Requested-With": "XMLHttpRequest" };
      const hit = xsrf && document.cookie.split("; ").find((c) => c.startsWith(xsrf + "="));
      if (hit) headers["X-XSRF-TOKEN"] = decodeURIComponent(hit.slice(xsrf.length + 1));
      Object.assign(init, { method: "POST", headers, body: body || "{}" });
      if (referrer) init.referrer = referrer;
    }
    const r = await fetch(u, init);
    const out = { status: r.status, text: await r.text() };
    if (r.redirected) out.landed = r.url;   // 平台把请求转去了别的地址（登录页、排队页）
    return out;
  } catch (e) {
    // 跟着跳转失败（比如被转去 http 的排队页，被浏览器拦下）：不跟跳转再问一次，确认是不是被转走了
    try {
      const r2 = await fetch(u, { credentials: "include", redirect: "manual", method: method === "POST" ? "POST" : "GET",
                                  headers: method === "POST" ? { "Content-Type": "application/json" } : undefined,
                                  body: method === "POST" ? (body || "{}") : undefined });
      if (r2.type === "opaqueredirect") return { status: 0, text: "", redirectedAway: true };
    } catch (_) { /* 真的是网络问题 */ }
    return { error: String(e), network: true };
  }
}

async function runInPageInner(job) {
  const site = SITES[job.launch];
  if (job.cookie && (site.HTTPONLY || []).includes(job.cookie)) {   // HttpOnly 的那一个：只读登记过的名字，且只读发射台所在的站点
    const c = await chrome.cookies.get({ url: new URL(job.launch).origin + "/", name: job.cookie });
    return { value: c ? c.value : "" };
  }
  let last = null;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const tab = await launchTab(job.launch);
      const [res] = await chrome.scripting.executeScript(job.cookie
        ? { target: { tabId: tab.id }, world: "MAIN", args: [job.cookie], func: pageReadCookie }
        : { target: { tabId: tab.id }, world: "MAIN", func: pageFetch,
            args: [job.url, job.method || "GET", job.body || "", site.REFERRER || "", site.XSRF || ""] });
      const out = res && res.result;
      if (out && !out.network) return out;
      last = (out && out.error) || "页面没有返回结果";
    } catch (e) {
      if (e instanceof NotLanded) return { error: e.message, notLanded: true };   // 没登录或没权限：重试没用
      last = String(e);                 // 发射台可能被丢弃/关闭了：下一轮换一个新的
      // 页面打不开每次要等 25 秒：最多试两次，赶在命令行 60 秒超时之前把原因报回去
      if (e instanceof PageNotOpened && attempt >= 1) break;
    }
    log("请求失败，准备重试", attempt + 1, last);
    await sleep(1500 * (attempt + 1));
  }
  return { error: "请求失败（已重试）：" + last };
}

function browserInfo() {
  const m = /(Chrome|Edg)\/([\d.]+)/.exec(navigator.userAgent) || [];
  return `${m[1] === "Edg" ? "Edge" : "Chrome"} ${m[2] || ""}`.trim();
}

async function handle(job) {
  if (!allowed(job)) return { id: job.id, error: "插件拒绝：只允许已登记平台的只读接口。" };
  try { return { id: job.id, browser: browserInfo(), ...(await runInPage(job)) }; }
  catch (e) { return { id: job.id, error: "插件执行失败：" + String(e) }; }
}

async function loop() {
  if (running) return;
  running = true;
  log("开始探测本机服务");
  let misses = 0;
  try {
    while (true) {
      if (!base) base = await findBridge();
      if (!base) {
        state.connected = false;
        // 没有命令行在等：每 2 秒探一次本机端口（只访问 127.0.0.1，没有任何外网流量）。
        // 这样命令行一启动就能被立刻发现，不用等 30 秒闹钟。空闲超过 10 分钟就退回闹钟，省资源。
        idleSince = idleSince || Date.now();
        if (Date.now() - idleSince > 10 * 60 * 1000) { idleSince = 0; break; }
        await sleep(2000);
        continue;
      }
      idleSince = 0;
      const t0 = Date.now();
      let r;
      try { r = await fetch(`${base}/next?wait=20&v=${VERSION}`, { headers: HEADERS }); }
      catch (_) { base = null; state.connected = false; break; }
      state.connected = true;
      if (r.status === 204) {
        // 正常情况下服务端会挂起约 20 秒才回 204；如果回得太快（对面不对劲），退避，绝不空转
        if (Date.now() - t0 < 1000) { misses += 1; await sleep(Math.min(5000, 500 * misses)); if (misses > 20) { base = null; break; } }
        else misses = 0;
        continue;
      }
      if (!r.ok) { base = null; break; }
      misses = 0;
      const job = await r.json();
      log("收到任务", job.cookie ? "读 " + job.cookie : (job.method || "GET") + " " + new URL(job.url).pathname);
      state.lastJob = Date.now(); state.jobs += 1;
      const out = await handle(job);
      try { await fetch(`${base}/result`, { method: "POST", headers: { ...HEADERS, "Content-Type": "text/plain" }, body: JSON.stringify(out) }); }
      catch (e) { state.lastError = String(e); base = null; break; }
    }
  } finally { running = false; }
}

// 唤醒：每 30 秒一次的闹钟、平台页面每几秒发来的「心跳」、以及用户打开平台页面时
log("插件后台已启动，id =", chrome.runtime.id);
chrome.alarms.create("taobao-cli-poll", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((a) => { if (a.name === "taobao-cli-poll") loop(); });
chrome.runtime.onMessage.addListener((msg, _s, reply) => {
  if (msg && msg.type === "tick") loop();
  if (msg && msg.type === "status") reply({ ...state, base });
});
chrome.runtime.onStartup.addListener(loop);
chrome.runtime.onInstalled.addListener(loop);
chrome.tabs.onUpdated.addListener((_id, info, tab) => {
  if (info.status === "complete" && tab.url && Object.keys(SITES).some((u) => tab.url.startsWith(new URL(u).origin + "/"))) loop();
});
