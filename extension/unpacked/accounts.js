// 账号切换：把一个账号的登录 cookie 存在插件里，要用哪个就换上哪个。
// 登录 cookie 只在这个插件里存取，不交给命令行、不发往任何地方；命令行只能说「列出」「保存为某名字」「换成某名字」。
// 账号是淘宝系的：淘宝、天猫、千牛、生意参谋、达摩盘、万相台共用一套登录。

const SCOPES = {
  taobao: { label: "淘宝/天猫", domains: ["taobao.com", "tmall.com", "tmall.hk", "alimama.com"], login: "https://login.taobao.com/",
            // 检查页：掉线时服务器直接转去登录页（10/11 校准过）。生意参谋的登录单独过期，千牛在线时它也可能要重登，所以两个都查
            checks: [["千牛", "https://myseller.taobao.com/home.htm"], ["生意参谋", "https://sycm.taobao.com/portal/home.htm"]] },
};

// 判断「是谁」用的 cookie：账号编号、昵称（子账号是「主账号:子账号」）
const ID_COOKIES = { taobao: ["unb"] };
const NICK_COOKIES = { taobao: ["sn", "_nk_", "tracknick", "lgc"] };

function unescapeNick(v) {
  let s = v || "";
  try { s = decodeURIComponent(s); } catch (_) {}
  return s.replace(/\\u([0-9a-fA-F]{4})/g, (_, h) => String.fromCharCode(parseInt(h, 16)));
}

async function scopeCookies(scope) {
  const seen = new Map();
  for (const d of SCOPES[scope].domains) {
    for (const c of await chrome.cookies.getAll({ domain: d })) {
      if (c.partitionKey) continue;   // 分区 cookie（第三方嵌入用）不是登录态
      seen.set(`${c.domain}|${c.path}|${c.name}`, c);
    }
  }
  return [...seen.values()];
}

function pick(cookies, names) {
  for (const n of names) {
    const c = cookies.find((x) => x.name === n && x.value);
    if (c) return c.value;
  }
  return "";
}

function whoIs(scope, cookies) {
  const uid = pick(cookies, ID_COOKIES[scope]);
  return { uid: uid ? unescapeNick(uid) : "", nick: unescapeNick(pick(cookies, NICK_COOKIES[scope])) };
}

function cookieUrl(c) {
  return `https://${c.domain.replace(/^\./, "")}${c.path || "/"}`;
}

async function setCookie(c) {
  const d = { url: cookieUrl(c), name: c.name, value: c.value, path: c.path, secure: c.secure,
              httpOnly: c.httpOnly, sameSite: c.sameSite, storeId: c.storeId };
  if (!c.hostOnly) d.domain = c.domain;
  if (!c.session && c.expirationDate) d.expirationDate = c.expirationDate;
  await chrome.cookies.set(d);
}

// 操作记录：每次保存、切换、登录新账号、删除、检查记一行（只有账号昵称和数量，没有 cookie 值），写进插件的本地日志（background.js 的 journal）。tb account log 能看
async function note(entry) {
  await journal({ kind: "account", ...entry });
}

function idCount(scope, cookies) {   // 还剩几个账号编号 cookie（清干净应为 0）
  return cookies.filter((c) => ID_COOKIES[scope].includes(c.name)).length;
}

async function loadVault() {
  const { accounts = {}, activeAccount = {} } = await chrome.storage.local.get(["accounts", "activeAccount"]);
  for (const s of Object.keys(SCOPES)) accounts[s] = accounts[s] || {};
  return { accounts, activeAccount };
}

async function saveVault(v) {
  await chrome.storage.local.set({ accounts: v.accounts, activeAccount: v.activeAccount });
}

// 浏览器里现在登录的账号如果已经存过，把存档换成最新的 cookie（平台会不断换发新的，存档跟着走）
async function refreshCurrent(scope, v, cookies) {
  const me = whoIs(scope, cookies);
  if (!me.uid) return null;
  const name = Object.keys(v.accounts[scope]).find((n) => v.accounts[scope][n].uid === me.uid);
  if (!name) return null;
  Object.assign(v.accounts[scope][name], { cookies, nick: me.nick, savedAt: Date.now() });
  v.activeAccount[scope] = name;
  return name;
}

// 换走或收起现在的账号之前：存过的更新成最新登录；没存过的按昵称自动存下，免得登录被丢掉
async function keepCurrent(scope, v, cookies) {
  const me = whoIs(scope, cookies);
  if (!me.uid) return null;
  const known = await refreshCurrent(scope, v, cookies);
  if (known) return known;
  let name = me.nick || me.uid;
  for (let i = 2; v.accounts[scope][name]; i++) name = `${me.nick || me.uid}（${i}）`;
  v.accounts[scope][name] = { uid: me.uid, nick: me.nick, savedAt: Date.now(), cookies };
  await note({ op: "autosave", scope, name, nick: me.nick, cookies: cookies.length });
  return name;
}

function summary(scope, name, a, active) {
  const expired = !a.cookies.some((c) => ID_COOKIES[scope].includes(c.name)
    && (c.session || !c.expirationDate || c.expirationDate * 1000 > Date.now()));
  return { scope, name, nick: a.nick, uid: a.uid, savedAt: a.savedAt, active: name === active, expired,
           alive: a.alive, how: a.how, checkedAt: a.checkedAt };
}

async function accountList() {
  const v = await loadVault();
  const out = { scopes: {}, current: {} };
  for (const scope of Object.keys(SCOPES)) {
    const cookies = await scopeCookies(scope);
    await refreshCurrent(scope, v, cookies);
    const me = whoIs(scope, cookies);
    out.current[scope] = { label: SCOPES[scope].label, nick: me.nick, uid: me.uid, loggedIn: !!me.uid };
    out.scopes[scope] = Object.entries(v.accounts[scope])
      .map(([n, a]) => summary(scope, n, a, me.uid && a.uid === me.uid ? n : null));
  }
  await saveVault(v);
  return out;
}

async function accountSave(scope, name) {
  if (!SCOPES[scope]) throw new Error(`没有这一组：${scope}`);
  name = (name || "").trim();
  const v = await loadVault();
  const cookies = await scopeCookies(scope);
  const me = whoIs(scope, cookies);
  if (!me.uid) throw new Error(`这个浏览器里没有登录${SCOPES[scope].label}，先登录再保存。`);
  name = name || me.nick || me.uid;
  // 同一个账号只存一份：之前用别的名字存过，就改成新名字
  for (const [n, a] of Object.entries(v.accounts[scope])) if (a.uid === me.uid && n !== name) delete v.accounts[scope][n];
  const other = v.accounts[scope][name];
  if (other && other.uid !== me.uid) throw new Error(`「${name}」已经存的是另一个账号（${other.nick}），换个名字。`);
  v.accounts[scope][name] = { uid: me.uid, nick: me.nick, savedAt: Date.now(), cookies };
  v.activeAccount[scope] = name;
  await saveVault(v);
  await note({ op: "save", scope, name, nick: me.nick, cookies: cookies.length });
  return { scope, name, nick: me.nick, uid: me.uid };
}

async function accountUse(scope, name) {
  if (!SCOPES[scope]) throw new Error(`没有这一组：${scope}`);
  const v = await loadVault();
  const target = v.accounts[scope][name];
  if (!target) throw new Error(`没有存过「${name}」。已存的：${Object.keys(v.accounts[scope]).join("、") || "无"}`);
  const current = await scopeCookies(scope);
  await keepCurrent(scope, v, current);   // 换走之前，先把现在这个账号存好（没存过的自动存）
  await saveVault(v);
  const before = whoIs(scope, current);
  if (before.uid === target.uid) return { scope, name, nick: target.nick, uid: target.uid, already: true };
  const removeFailed = await clearScope(current);
  const leftIds = idCount(scope, await scopeCookies(scope));
  const now = Date.now() / 1000;
  let failed = 0;
  for (const c of target.cookies) {
    if (!c.session && c.expirationDate && c.expirationDate < now) continue;
    try { await setCookie(c); } catch (e) { failed += 1; log("写回 cookie 失败", c.domain, c.name, String(e)); }
  }
  v.activeAccount[scope] = name;
  await saveVault(v);
  const after = whoIs(scope, await scopeCookies(scope));
  await note({ op: "use", scope, name, before: before.nick, after: after.nick, removed: current.length, removeFailed, leftIds,
               set: target.cookies.length - failed, failed });
  if (after.uid !== target.uid) throw new Error(`换成「${name}」后没有读到这个账号的登录（写回失败 ${failed} 个）。`);
  return { scope, name, nick: target.nick, uid: target.uid, failed };
}

async function clearScope(cookies) {
  let failed = 0;
  for (const c of cookies) {
    try {
      const r = await chrome.cookies.remove({ url: cookieUrl(c), name: c.name, storeId: c.storeId });
      if (!r) failed += 1;
    } catch (e) { failed += 1; log("删 cookie 失败", c.domain, c.name, String(e)); }
  }
  return failed;
}

// 要登录另一个账号：先把现在这个存好，再只从浏览器里拿掉它的登录（不点退出，平台那边的登录还在，之后换回来照样能用）
async function accountFresh(scope) {
  if (!SCOPES[scope]) throw new Error(`没有这一组：${scope}`);
  const v = await loadVault();
  const current = await scopeCookies(scope);
  const me = whoIs(scope, current);
  await keepCurrent(scope, v, current);
  await saveVault(v);
  const failed = await clearScope(current);
  delete v.activeAccount[scope];
  await saveVault(v);
  const left = await scopeCookies(scope);
  await note({ op: "fresh", scope, before: me.nick, removed: current.length, failed, left: left.length, leftIds: idCount(scope, left) });
  if (idCount(scope, left)) throw new Error(`没能从浏览器里拿掉现在的登录（还剩 ${idCount(scope, left)} 个账号 cookie），先别去登录新账号。`);
  return { scope, loginUrl: SCOPES[scope].login };
}

// 检查存下的账号还在不在：带着它的登录访问一次卖家后台首页，正常打开 = 还在，被转去登录页 = 掉线了。
// 不动浏览器里现在的登录：这次请求的 Cookie 头由临时规则换成这个账号的，平台回来的 Set-Cookie 也拦掉，不进浏览器。
function cookieHeader(cookies, url) {
  const u = new URL(url);
  return cookies.filter((c) => {
    const d = c.domain.replace(/^\./, "");
    const hostOk = c.hostOnly ? u.hostname === d : (u.hostname === d || u.hostname.endsWith("." + d));
    return hostOk && (c.path || "/") === "/" && (!c.expirationDate || c.session || c.expirationDate * 1000 > Date.now());
  }).map((c) => `${c.name}=${c.value}`).join("; ");
}

const CHECK_LOGIN = /(^|\.)(login\w*|passport|havanalogin)\./;   // loginmyseller.taobao.com 这类卖家登录页也算   // 最后停在这些站点 = 被转去登录了

const CHECK_LOGIN_PATH = /^\/custom\/login\.htm/;   // 生意参谋掉线转去的是自己域名下的 sycm.taobao.com/custom/login.htm

let checkRule = 9000;
async function probePage(scope, cookies, page) {
  const url = `${page}?tbcli_check=${Date.now()}${Math.random().toString(36).slice(2, 8)}`;
  const id = ++checkRule;
  // 这一两秒里，插件后台自己发往这一组域名的请求都换成这个账号的 Cookie（跟着跳转的每一步都带上），平台回的 Set-Cookie 全部拦掉
  // 会话规则在插件后台重启后还在，而编号从头数：先删同号的旧规则再加
  await chrome.declarativeNetRequest.updateSessionRules({ removeRuleIds: [id], addRules: [{
    id, priority: 1,
    condition: { requestDomains: SCOPES[scope].domains, tabIds: [chrome.tabs.TAB_ID_NONE], initiatorDomains: [chrome.runtime.id] },
    action: { type: "modifyHeaders",
              requestHeaders: [{ header: "cookie", operation: "set", value: cookieHeader(cookies, url) }],
              responseHeaders: [{ header: "set-cookie", operation: "remove" }] },
  }] });
  try {
    const r = await fetch(url, { credentials: "omit", cache: "no-store", signal: AbortSignal.timeout(10000) });   // 页面一直不返回（比如排队页）就算查不出，别把整个检查挂住
    const u = new URL(r.url);
    if (CHECK_LOGIN.test(u.hostname) || CHECK_LOGIN_PATH.test(u.pathname)) return false;
    return r.ok ? true : null;
  } catch (_) {
    return null;
  } finally {
    await chrome.declarativeNetRequest.updateSessionRules({ removeRuleIds: [id] });
  }
}

// 每个检查页都打开一次：全部正常才算在线；哪个被转去登录页就说哪个要重新登录
async function probe(scope, cookies) {
  const res = [];
  for (const [name, page] of SCOPES[scope].checks) res.push([name, await probePage(scope, cookies, page)]);
  const dead = res.filter(([, ok]) => ok === false).map(([n]) => n);
  const unknown = res.filter(([, ok]) => ok === null).map(([n]) => n);
  if (dead.length === res.length) return { alive: false, how: "已掉线" };
  if (dead.length) return { alive: false, how: `${dead.join("、")}要重新登录（${res.filter(([, ok]) => ok).map(([n]) => n).join("、")}还在）` };
  if (unknown.length) return { alive: null, how: `${unknown.join("、")}打不开，查不出` };
  return { alive: true, how: res.length > 1 ? `${res.map(([n]) => n).join("、")}都正常` : "后台正常打开" };
}

async function accountCheck(scope, name) {
  const v = await loadVault();
  const out = [];
  for (const s of scope ? [scope] : Object.keys(SCOPES)) {
    for (const [n, a] of Object.entries(v.accounts[s])) {
      if (name && n !== name) continue;
      const r = await probe(s, a.cookies);
      a.checkedAt = Date.now(); a.alive = r.alive; a.how = r.how;
      out.push({ scope: s, name: n, nick: a.nick, ...r });
    }
  }
  await saveVault(v);
  await note({ op: "check", results: out.map((r) => `${r.name}:${r.alive}`).join(" ") });
  return out;
}

async function accountRemove(scope, name) {
  const v = await loadVault();
  if (!v.accounts[scope] || !v.accounts[scope][name]) throw new Error(`没有存过「${name}」`);
  const nick = v.accounts[scope][name].nick;
  delete v.accounts[scope][name];
  if (v.activeAccount[scope] === name) delete v.activeAccount[scope];
  await saveVault(v);
  await note({ op: "remove", scope, name, nick });
  return { scope, name, removed: true };
}

// 命令行发来的账号任务：{account: {op, scope, name}}。返回值里绝不带 cookie。
async function handleAccount(req) {
  const scope = req.scope || "taobao";
  if (req.op === "list") return await accountList();
  if (req.op === "save") return await accountSave(scope, req.name);
  if (req.op === "use") return await accountUse(scope, req.name);
  if (req.op === "fresh") return await accountFresh(scope);
  if (req.op === "check") return await accountCheck(req.scope || "", req.name || "");
  if (req.op === "log") return (await readJournal()).filter((e) => e.kind === "account").slice(-100);
  throw new Error(`不认识的账号操作：${req.op}`);   // 删除只能在插件弹窗里点
}

// 每 30 分钟把正在用的账号的最新登录存一次（只读浏览器自己的 cookie，不发任何请求）
chrome.alarms.create("taobao-cli-accounts", { periodInMinutes: 30 });
chrome.alarms.onAlarm.addListener(async (a) => {
  if (a.name !== "taobao-cli-accounts") return;
  const v = await loadVault();
  for (const scope of Object.keys(SCOPES)) await refreshCurrent(scope, v, await scopeCookies(scope));
  await saveVault(v);
});
