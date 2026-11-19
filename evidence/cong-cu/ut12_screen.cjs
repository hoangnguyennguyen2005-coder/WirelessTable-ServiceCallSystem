// UT-12 "1-màn hình" (guide §4.3) driven in a real Chrome window via Playwright.
const { chromium } = require("D:/Projects/PBL4/frontend/node_modules/playwright-core");
const fs = require("fs");
const path = require("path");
const OUT = "D:/Projects/PBL4/evidence/UT-12";
const B = "http://127.0.0.1:8000";
const hhmmss = (d = new Date()) => d.toTimeString().slice(0, 8) + "." + String(d.getMilliseconds()).padStart(3, "0");

(async () => {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const FRAMES = path.join(OUT, "dong-ho-cho");
  fs.mkdirSync(FRAMES, { recursive: true });
  let frame = 0, nextFrame = 0;
  const page = await context.newPage();
  await page.goto(B);
  await page.getByRole("button", { name: "Bàn mô phỏng", exact: true }).click();
  await page.getByRole("button", { name: "Gọi đồng thời 4 bàn" }).click();
  await page.getByRole("button", { name: "Tổng quan", exact: true }).click();
  await page.locator(".queue-item").nth(3).waitFor();

  const log = [];
  const start = Date.now();
  await page.screenshot({ path: path.join(OUT, "UT12_1-man-hinh_a.png") });
  while (Date.now() - start < 10500) {
    const ages = await page.locator(".queue-item time").allTextContents();
    log.push(`${hhmmss()}  ${ages.join("  ")}`);
    if (Date.now() - start >= nextFrame) {
      frame += 1;
      nextFrame += 1000;
      const name = `frame-${String(frame).padStart(2, "0")}_${hhmmss().replace(/[:.]/g, "-")}.png`;
      await page.locator(".queue").first().screenshot({ path: path.join(FRAMES, name) }).catch(() =>
        page.screenshot({ path: path.join(FRAMES, name) }));
    }
    if (Math.abs(Date.now() - start - 5000) < 120 && !fs.existsSync(path.join(OUT, "UT12_1-man-hinh_b.png")))
      await page.screenshot({ path: path.join(OUT, "UT12_1-man-hinh_b.png") });
    await page.waitForTimeout(200);
  }
  // Each change of the first timer: when did it happen and by how much did it step?
  const changes = [];
  let previous = null;
  for (const line of log) {
    const [time, age] = line.split(/\s+/);
    if (age !== previous) changes.push([time, age]);
    previous = age;
  }
  const seconds = (t) => t.split(":").reduce((a, v) => a * 60 + Number(v), 0);
  const steps = changes.slice(1).map((c, i) => [
    (seconds(c[0]) - seconds(changes[i][0])).toFixed(2),
    seconds(c[1]) - seconds(changes[i][1]),
  ]);
  const summary = [
    `UT-12 buoc 1-man-hinh — mau dong ho cho tren man hinh quan ly (${new Date().toISOString()})`,
    `Lay mau moi 200 ms trong ${((Date.now() - start) / 1000).toFixed(1)} s; 4 ban dang cho, cot = 4 dong ho trong Hang doi phuc vu.`,
    "",
    ...log,
    "",
    "Cac lan dong ho ban 1 doi gia tri (gio may tinh -> gia tri hien):",
    ...changes.map((c) => `  ${c[0]} -> ${c[1]}`),
    `Khoang cach giua cac lan doi (giay thuc): ${steps.map((s) => s[0]).join(", ")}`,
    `Moi lan doi tang (giay): ${steps.map((s) => s[1]).join(", ")}`,
  ];
  fs.writeFileSync(path.join(OUT, "dong-ho-cho-mau.txt"), summary.join("\r\n"), "utf8");

  await page.getByRole("button", { name: "Bàn mô phỏng", exact: true }).click();
  await page.getByRole("button", { name: "Tua +300 giây · chỉ đồng hồ demo" }).click();
  await page.getByRole("button", { name: "Tổng quan", exact: true }).click();
  await page.getByText(/Nhắc: 4 yêu cầu/).waitFor({ timeout: 15000 });
  await page.screenshot({ path: path.join(OUT, "UT12_nhac-5-phut.png"), fullPage: true });
  const queue = await page.locator(".queue-item strong").allTextContents();
  fs.appendFileSync(path.join(OUT, "dong-ho-cho-mau.txt"),
    `\r\n\r\nSau khi tua +300 s: "${(await page.getByText(/Nhắc: 4 yêu cầu/).textContent()).trim()}"\r\nThu tu hang doi: ${queue.join(" | ")}\r\n`, "utf8");

  await context.close();
  await browser.close();
  console.log(summary.slice(-3).join("\n"));
  console.log("queue after +300:", queue.join(" | "));
})().catch((e) => { console.error(e); process.exit(1); });
