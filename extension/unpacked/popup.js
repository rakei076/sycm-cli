// 命令行打招呼时报的名字 -> 平台（显示「正在服务」哪个工具）
const TOOLS = [
  ["sycm-cli", "生意参谋", "店铺经营数据"],
  ["alimama-cli", "万相台", "广告报表、在投计划（只读）"],
  ["qianniu-cli", "千牛", "评价、商品、物流"],
  ["dmp-cli", "达摩盘", "人群资产、画像"],
  ["voc-cli", "taobao-voc", "竞品评价、问大家（买家账号）"],
];

chrome.runtime.sendMessage({ type: "status" }, (st) => {
  const el = document.getElementById("s");
  if (!st) { el.textContent = "后台没有响应，请稍后再点开。"; return; }
  const name = (TOOLS.find((t) => t[0] === st.app) || [st.app, st.app])[1];
  el.innerHTML = st.connected
    ? `<span class="dot on"></span>正在服务：${name}（已处理 ${st.jobs} 个请求）`
    : `<span class="dot"></span>待命中：没有正在运行的命令`;
});

// ---- 账号切换 ----
const LOGIN_URL = { taobao: "https://login.taobao.com/" };
const accMsg = (text) => { document.getElementById("msg").textContent = text || ""; };
const askBg = (msg) => new Promise((ok) => chrome.runtime.sendMessage({ type: "account", ...msg }, ok));

function button(text, onClick) {
  const b = document.createElement("button");
  b.textContent = text;
  b.addEventListener("click", onClick);
  return b;
}

let checking = false;   // 打开弹窗时自动检查一遍账号还在不在；检查完之前圆点是灰的

function dot(a) {
  const d = document.createElement("span");
  d.className = "st " + (checking ? "" : a.alive === false ? "off" : a.alive ? "on" : "");
  d.title = checking ? "正在检查" : a.alive === false ? `${a.how || "已掉线"}：点「重新登录」` : a.alive ? "在线" : a.how || "还没检查";
  return d;
}

async function renderAccounts() {
  const res = await askBg({ op: "list" });
  const box = document.getElementById("accounts");
  box.textContent = "";
  if (!res || res.error) { accMsg(res ? res.error : "后台没有响应"); return; }
  for (const [scope, cur] of Object.entries(res.ok.current)) {
    const sec = document.createElement("div");
    sec.className = "acc";
    const h = document.createElement("h2");
    h.textContent = `${cur.label}账号`;
    sec.append(h);
    const saved = cur.loggedIn && res.ok.scopes[scope].some((a) => a.uid === cur.uid);
    if (!saved) {   // 存过的账号用绿色名字表示「现在用的是它」；没存过或没登录才单独写一行
      const now = document.createElement("div");
      now.innerHTML = cur.loggedIn ? `现在登录：<b class="cur"></b>（还没存）` : `<span class="bad">现在没有登录</span>`;
      if (cur.loggedIn) now.querySelector("b").textContent = cur.nick || cur.uid;
      sec.append(now);
    }
    for (const a of res.ok.scopes[scope]) {
      const row = document.createElement("div");
      row.className = "row";
      const n = document.createElement("span");
      n.className = "n" + (a.active ? " cur" : "");
      n.textContent = a.name;
      n.title = a.nick;
      row.append(n);
      if (a.alive === false && !checking && a.how && a.how !== "已掉线") {   // 只有一部分后台掉线（比如千牛在、生意参谋要重登）：写出来
        const w = document.createElement("small");
        w.className = "bad";
        w.textContent = a.how.split("（")[0];
        row.append(w);
      }
      if (a.alive === false && !checking) row.append(button("重新登录", async () => {
        // 掉线的账号：把现在的登录先存好、从浏览器里收起来，再打开登录页；登录的还是这个号，插件会自动把它的存档换成新的登录
        const r = await askBg({ op: "fresh", scope });
        if (r && r.error) { accMsg(r.error); return; }
        chrome.tabs.create({ url: r.ok.loginUrl });
        window.close();
      }));
      else if (!a.active) row.append(button("切换", async () => {
        accMsg("正在切换…");
        const r = await askBg({ op: "use", scope, name: a.name });
        accMsg(r && r.error ? r.error : `已换成「${a.name}」，刷新后台页面后生效。`);
        renderAccounts();
      }));
      row.append(button("删除", async () => {
        if (!confirm(`删除存下的「${a.name}」？浏览器里现在的登录不受影响。`)) return;
        const r = await askBg({ op: "remove", scope, name: a.name });
        accMsg(r && r.error ? r.error : "");
        renderAccounts();
      }));
      row.append(dot(a));
      sec.append(row);
    }
    if (cur.loggedIn) {
      // 加新账号不要点网页上的「退出」：那会让存下的这个账号失效。这里只把它从浏览器里收起来，再去登录新的
      const row = document.createElement("div");
      row.className = "row";
      row.append(button("登录新账号", async () => {
        const r = await askBg({ op: "fresh", scope });
        if (r && r.error) { accMsg(r.error); return; }
        chrome.tabs.create({ url: r.ok.loginUrl });
        window.close();
      }));
      sec.append(row);
    } else {
      const row = document.createElement("div");
      row.className = "row";
      row.append(button("去登录", () => { chrome.tabs.create({ url: LOGIN_URL[scope] }); window.close(); }));
      sec.append(row);
    }
    if (cur.loggedIn && !saved) {
      const row = document.createElement("div");
      row.className = "row";
      const input = document.createElement("input");
      input.type = "text";
      input.placeholder = `给现在这个账号起个名字，如「主店」`;
      row.append(input, button("保存", async () => {
        const r = await askBg({ op: "save", scope, name: input.value });
        accMsg(r && r.error ? r.error : `已保存为「${r.ok.name}」。`);
        renderAccounts();
      }));
      sec.append(row);
    }
    box.append(sec);
  }
}

const FRESH = 10 * 60 * 1000;   // 10 分钟内查过就直接显示上次的结果，不再重查（每个淘宝号要开两个后台页面，查一遍要好几秒）

async function openPopup() {
  const res = await askBg({ op: "list" });
  const all = res && res.ok ? Object.values(res.ok.scopes).flat() : [];
  if (all.length && all.every((a) => a.checkedAt && Date.now() - a.checkedAt < FRESH)) { renderAccounts(); return; }
  checking = true;
  await renderAccounts();
  const r = await askBg({ op: "check" });
  checking = false;
  if (r && r.error) accMsg(r.error);
  renderAccounts();
}
openPopup();
