const fs = require("node:fs");
const assert = require("node:assert/strict");
const root = "pages/factor-lab-dashboard/";
const config = fs.readFileSync(root + "config.js", "utf8");
const html = fs.readFileSync(root + "index.html", "utf8");
const app = fs.readFileSync(root + "app.js", "utf8");
assert(config.includes('window.FACTOR_LAB_API_HOST = "https://factor.liangjun.net.cn"'),
  "Pages must connect to the existing server API, not an old Supabase mirror or demo mode");
assert(!html.includes('src="./config.local.js"'), "Pages must not request a server-only config");
assert(html.includes("strategyBuilderView") && html.includes("strategyBoardView"));
assert(app.includes("loginThroughApi") && app.includes("headers.Authorization"));
assert(!/sb_secret_|sbp_[A-Za-z0-9]+/.test(config));
for (const asset of ["factor-lab-logo.png", "echarts.min.js"]) {
  assert(fs.statSync(root + "assets/" + asset).size > 0);
}
console.log(JSON.stringify({ checks: 7, result: "passed" }));
