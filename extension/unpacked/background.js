// taobao-cli 取数桥（后台）
// 一个插件服务所有本机工具：tb（生意参谋 / 万相台 / 千牛 / 达摩盘 / 1688）、dmp-cli、taobao-voc。
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
//   POSTS    允许的 POST 接口：字符串 = 精确路径，正则 = 只为带编号的路径（必须和发射台同域）；没有这一项的平台不放行任何 POST
//   COOKIES  允许读的 cookie；HTTPONLY = 其中页面脚本读不到、要用 chrome.cookies 读的那几个
const SITES = {
  "https://dmp.taobao.com/robots.txt": {
    ALLOWED: [/^https:\/\/dmp\.taobao\.com\/api_2\//, /^https:\/\/dmp\.advgateway\.taobao\.com\/api\//],
    WRITE: /(^|\/)(add|create|update|delete|del|remove|save|submit|bind|unbind|cancel|set|apply|edit|upload|push|send|sync|copy|move|rename|batch|start|stop|pay|recharge|buy|generate|subscription)(\/|$|\?)/i,
    // dmp-cli 的人群画像：这几个接口用 POST 传查询条件，但只读（网页「画像透视」用的就是它们）
    POSTS: ["/api_2/analysis/insight/tag/list", "/api_2/analysis/insight/feature", "/api_2/analysis/insight/coverage",
            /^\/api_2\/analysis\/tag\/\d+$/],
    COOKIES: TOKENS,
  },
  "https://myseller.taobao.com/robots.txt": {
    ALLOWED: [/^https:\/\/h5api\.m\.taobao\.com\/h5\//, /^https:\/\/ascp-plan-control-tower-web\.dchain-api-proxy\.taobao\.com\/data\/lg\//],
    WRITE: /(update|create|delete|modify|save|add|remove|edit|submit|send|post|set|operate|publish|cancel|confirm|pay|refund)/i,
    COOKIES: TOKENS,
  },
  "https://sycm.taobao.com/robots.txt": {
    ALLOWED: [/^https:\/\/sycm\.taobao\.com\//],
    WRITE: /(^|[/.])(add|create|update|delete|remove|save|submit|cancel|set|edit|upload|apply|bind|unbind)([/.]|$)/i,
    COOKIES: TOKENS,
  },
  // 万相台：读取接口全是 POST。只放行下面这些查询接口；关停广告（/adgroup/updatePart.json）等写接口不在清单里，插件永远发不出去。
  "https://one.alimama.com/robots.txt": {
    POSTS: [
      "/member/checkAccess.json", "/account/checkRealBalance.json", "/activity/getActivityList.json",
      "/report/query.json", "/report/chargeSum.json", "/report/campaign/findPage.json", "/report/adgroup/findPage.json",
      "/campaign/horizontal/findPage.json", "/adgroup/horizontal/findPage.json",
    ],
    REFERRER: "https://one.alimama.com/index.html",
    XSRF: "XSRF-TOKEN",   // 页面自己的请求会把这个 cookie 放进 X-XSRF-TOKEN 头，这里照做
    COOKIES: [],
  },
  // 1688 订单：全部走同一个 MTOP 接口，读写只能靠参数里的 serviceId 区分，所以除了接口地址还要 serviceId 白名单
  "https://air.1688.com/robots.txt": {
    ALLOWED: [/^https:\/\/h5api\.m\.1688\.com\/h5\/mtop\.1688\.trading\.dataline\.service\//],
    WRITE: /(update|create|delete|remove|modify|save|submit|cancel|operate|refund|close|pay)/i,
    SERVICES: ["OrderListDataLineService.sellerOrderList", "OrderListDataLineService.sellerOrderStat"],
    COOKIES: TOKENS,
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
    return !!site.POSTS && u.origin === new URL(job.launch).origin && typeof job.body === "string" && job.body.length <= 200000
      && site.POSTS.some((p) => (typeof p === "string" ? p === u.pathname : p.test(u.pathname)));
  }
  if (job.method && job.method !== "GET") return false;
  if (!site.ALLOWED || !site.ALLOWED.some((re) => re.test(job.url))) return false;
  if (site.WRITE.test(u.pathname)) return false;
  if (site.SERVICES) {
    try { return site.SERVICES.includes(JSON.parse(u.searchParams.get("data")).serviceId); }
    catch (_) { return false; }
  }
  return true;
}
// ---- 放行规则结束 ----

const DEV_AUTO_RELOAD = false;   // build.py 只在开发版里改成 true
const BUILD = "eca56fef0bd1";        // build.py 写入构建号
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
  const t = await chrome.tabs.create({ url: launchUrl, active: false });
  const tab = await waitLanded(t.id, origin);
  if (!tab || !tab.url || new URL(tab.url).origin !== origin) {
    try { await chrome.tabs.remove(t.id); } catch (_) {}
    throw new NotLanded(`打开 ${origin} 时被带到了 ${tab && tab.url ? new URL(tab.url).host : "别的页面"}：这个浏览器里还没有登录这个平台。请先在这个 Chrome 里打开 ${origin} 登录一次。`);
  }
  helpers[launchUrl] = t.id;
  return tab;
}

// 等发射台加载完并停在平台自己的域名上（中途经过登录中转也算），最多 25 秒
function waitLanded(tabId, origin, ms = 25000) {
  return new Promise((resolve) => {
    const t0 = Date.now();
    const tick = async () => {
      let tab; try { tab = await chrome.tabs.get(tabId); } catch (_) { return resolve(null); }
      const home = tab.url && tab.url.startsWith(origin + "/");
      if ((tab.status === "complete" && home) || Date.now() - t0 > ms) return resolve(tab);
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
    return { status: r.status, text: await r.text() };
  } catch (e) { return { error: String(e), network: true }; }
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
      if (e instanceof NotLanded) return { error: e.message };   // 没登录：重试没用
      last = String(e);                 // 发射台可能被丢弃/关闭了：下一轮换一个新的
    }
    log("请求失败，准备重试", attempt + 1, last);
    await sleep(1500 * (attempt + 1));
  }
  return { error: "网络请求失败（重试 3 次仍失败）：" + last };
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
