// AT-07 row 2a, supplementary: how long until each indication is visible ON SCREEN.
// Three tabs watch at once; three cycles; every cycle is reported.
const { chromium } = require("D:/Projects/PBL4/frontend/node_modules/playwright-core");
const fs = require("fs");
const path = require("path");
const { spawn, execSync } = require("child_process");

const ROOT = "D:/Projects/PBL4";
const OUT = path.join(ROOT, "evidence/AT-07");
const B = "http://127.0.0.1:8000";
const PY = path.join(ROOT, ".venv/Scripts/python.exe");
const DATA = "data-at07-2a";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const lines = [];
const say = (s) => { lines.push(s); console.log(s); };
const get = async (p) => (await fetch(B + p)).json();
async function until(fn, timeout, step = 50) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try { if (await fn()) return Date.now() - start; } catch { /* retry */ }
    await sleep(step);
  }
  return null;
}

(async () => {
  fs.rmSync(path.join(ROOT, DATA), { recursive: true, force: true });
  const server = spawn(PY, ["tools/demo.py", "--mode", "simulation"], {
    cwd: ROOT, env: { ...process.env, PBL_DATA_DIR: DATA }, stdio: "ignore", windowsHide: true,
  });
  await until(() => get("/api/health"), 30000, 200);
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const sim = await context.newPage();
  const overview = await context.newPage();
  const history = await context.newPage();
  for (const p of [sim, overview, history]) await p.goto(B);
  await sim.getByRole("button", { name: "Bàn mô phỏng", exact: true }).click();
  await history.getByRole("button", { name: "Lịch sử", exact: true }).click();
  await history.getByRole("tab", { name: "Nhật ký sự kiện" }).click();

  say("AT-07 buoc 2a — do bo sung TREN MAN HINH (Chrome, 3 tab cung luc), " + new Date().toString());
  say("Moc 0 = luc bam 'Ngat gateway mo phong', bam NGAY SAU khi ban vua poll (truong hop xau nhat). Lay mau moi 50 ms. Ghi du ca 3 lan.");
  say("");
  for (const table of [1, 2, 3]) {
    const name = `Bàn ${String(table).padStart(2, "0")}`;
    await sim.getByLabel("Chọn bàn").selectOption({ label: name });
    const button = sim.getByRole("button", { name: "PHỤC VỤ Giữ 5 giây" });
    await button.focus();
    await sim.keyboard.down("Space");
    await sleep(5200);
    await sim.keyboard.up("Space");
    await sim.getByText("Trung tâm đã ghi nhận · đèn đỏ sáng").waitFor({ timeout: 15000 });
    await overview.getByRole("button", { name: new RegExp(`^${name} — `) }).click();
    await overview.getByRole("button", { name: "Xác nhận yêu cầu", exact: true }).click();
    await overview.getByText("Bàn báo đã hiển thị: đèn xanh").waitFor({ timeout: 20000 });
    await overview.getByLabel("Đóng chi tiết").click();
    // Worst case: disconnect right after the table's poll, so the silence starts at the fault.
    const seen = async () => (await get("/api/snapshot")).tables.find((t) => t.id === table).last_seen;
    const previous = await seen();
    await until(async () => (await seen()) !== previous, 10000, 20);
    const lastSeen = await seen();

    await sim.getByRole("button", { name: "Ngắt gateway mô phỏng" }).click();
    const t0 = Date.now();
    const sinceContact = (t0 / 1000 - lastSeen).toFixed(1);
    const card = overview.getByRole("button", { name: new RegExp(`^${name} — `) });
    const [a, b, c1, c2, api] = await Promise.all([
      until(() => sim.getByText(/Gateway đang ngắt/).first().isVisible(), 20000),
      until(() => sim.getByText("Mất liên lạc trung tâm · đỏ chớp đôi").isVisible(), 20000),
      until(async () => (await card.textContent()).includes("Mất liên lạc với bàn"), 20000),
      until(async () => (await history.locator("tbody tr").filter({ hasText: name })
        .filter({ hasText: /Mất liên lạc với bàn/ }).count()) > 0, 20000),
      until(async () => (await get(`/api/event-log?type=FAILURE&table_id=${table}`)).items
        .some((e) => (e.reason || "").includes("table_contact_lost")), 20000),
    ]);
    const s = (v) => (v === null ? "KHONG THAY trong 20 s" : (v / 1000).toFixed(1) + " s");
    say(`Lan ${table} (${name}; lan lien lac cuoi truoc khi ngat ${sinceContact} s):`);
    say(`  (a) dai 'Gateway dang ngat' tren man hinh ......... ${s(a)}`);
    say(`  (b) ban mo phong 'Mat lien lac trung tam' .......... ${s(b)}`);
    say(`  (c) Tong quan, the ban 'Mat lien lac voi ban' ...... ${s(c1)}`);
    say(`  (c) Nhat ky su kien hien dong mat lien lac .......... ${s(c2)}`);
    say(`      (doi chieu: API ghi FAILURE table_contact_lost .. ${s(api)})`);
    const worst = Math.max(...[b, c1, c2].map((v) => (v === null ? Infinity : v)));
    say(`  => ${worst <= 10000 ? "DAT" : "KHONG DAT"}: cham nhat ${s(worst === Infinity ? null : worst)} (gioi han 10 s)`);
    if (table === 1) {
      await sim.screenshot({ path: path.join(OUT, "AT07_2a_man-hinh_ban-mo-phong.png"), fullPage: true });
      await overview.screenshot({ path: path.join(OUT, "AT07_2a_man-hinh_tong-quan.png"), fullPage: true });
      await history.screenshot({ path: path.join(OUT, "AT07_2a_man-hinh_nhat-ky.png"), fullPage: true });
    }
    await sim.getByRole("button", { name: "Kết nối lại gateway" }).click();
    await sim.getByText("Quản lý đã xác nhận · đèn xanh sáng").waitFor({ timeout: 20000 });
    say("");
  }
  fs.writeFileSync(path.join(OUT, "2a-do-tren-man-hinh.txt"), lines.join("\r\n") + "\r\n", "utf8");
  await browser.close();
  execSync(`powershell -NoProfile -Command "$p=(Get-NetTCPConnection -LocalPort 8000 -State Listen).OwningProcess; Stop-Process -Id $p -Force"`);
  await sleep(1000);
  fs.rmSync(path.join(ROOT, DATA), { recursive: true, force: true });
  server.kill();
})().catch((e) => { console.error(e); process.exit(1); });
