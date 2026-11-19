const { chromium } = require("D:/Projects/PBL4/frontend/node_modules/playwright-core");
const fs = require("fs");
(async () => {
  const b = await chromium.launch({ channel: "chrome", headless: true });
  const p = await (await b.newContext({ viewport: { width: 1366, height: 900 } })).newPage();
  await p.goto("http://127.0.0.1:8000");
  await p.getByRole("button", { name: "Bàn mô phỏng", exact: true }).click();
  await p.getByRole("button", { name: "Gọi đồng thời 4 bàn" }).click();
  await p.getByRole("button", { name: "Tổng quan", exact: true }).click();
  await p.locator(".queue-item").nth(3).waitFor();
  const sec = (t) => t.split(":").reduce((a, v) => a * 60 + Number(v), 0);
  const prev = [null, null, null, null], bad = [], start = Date.now();
  let changes = 0, advanced = false;
  while (Date.now() - start < 40000) {
    if (!advanced && Date.now() - start > 20000) {
      advanced = true;
      await p.request.post("http://127.0.0.1:8000/api/sim/action", { data: { action: "advance", seconds: 300 } });
      await p.getByText(/Nhắc: 4 yêu cầu/).waitFor({ timeout: 5000 });
      prev.fill(null);
      continue;
    }
    const ages = (await p.locator(".queue-item time").allTextContents()).map(sec);
    ages.forEach((v, i) => {
      if (prev[i] !== null && v !== prev[i]) {
        changes++;
        if (v - prev[i] !== 1) bad.push(`${new Date().toTimeString().slice(0, 8)} ban ${i + 1}: ${prev[i]} -> ${v}`);
      }
      prev[i] = v;
    });
    await p.waitForTimeout(100);
  }
  const out = [`Do dai 40 s, 4 dong ho, lay mau 100 ms; tua +300 s o giay 20 (khong tinh buoc nhay do tua).`,
    `So lan doi gia tri: ${changes}; so lan KHONG phai +1: ${bad.length}`, ...bad];
  fs.writeFileSync("D:/Projects/PBL4/evidence/UT-12/dong-ho-cho-40s.txt", out.join("\r\n") + "\r\n", "utf8");
  console.log(out.join("\n"));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
