// 工具清单：命令行打招呼时报的名字 -> 平台、用途。勾掉的工具，这个浏览器就不再替它取数。
const TOOLS = [
  ["sycm-cli", "生意参谋", "店铺经营数据"],
  ["alimama-cli", "万相台", "广告报表、在投计划（只读）"],
  ["qianniu-cli", "千牛", "评价、商品、物流"],
  ["dmp-cli", "达摩盘", "人群资产、画像"],
  ["alibaba-cli", "1688", "订单统计"],
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

chrome.storage.local.get("off", ({ off = [] }) => {
  const box = document.getElementById("tools");
  for (const [app, platform, what] of TOOLS) {
    const row = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = !off.includes(app);
    cb.addEventListener("change", async () => {
      const cur = (await chrome.storage.local.get("off")).off || [];
      const next = cb.checked ? cur.filter((x) => x !== app) : [...new Set([...cur, app])];
      await chrome.storage.local.set({ off: next });
    });
    const text = document.createElement("span");
    text.innerHTML = `${platform} <small>${app} · ${what}</small>`;
    row.append(cb, text);
    box.append(row);
  }
});
