// 只做一件事：在平台页面开着时，每 3 秒告诉后台「我还在」，让后台尽快发现本机的命令行在等数据。不读页面内容。
setInterval(() => { try { chrome.runtime.sendMessage({ type: "tick" }); } catch (_) {} }, 3000);
