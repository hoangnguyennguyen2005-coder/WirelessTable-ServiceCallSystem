// AT-07 simulation rehearsal (guide §5.2–5.4), automated in Chrome via Playwright.
// Every check is recorded (pass or fail); nothing is asserted away.
const { chromium } = require("D:/Projects/PBL4/frontend/node_modules/playwright-core");
const fs = require("fs");
const path = require("path");
const { spawn, execSync } = require("child_process");

const ROOT = "D:/Projects/PBL4";
const OUT = path.join(ROOT, "evidence/AT-07");
const B = "http://127.0.0.1:8000";
const PY = path.join(ROOT, ".venv/Scripts/python.exe");
fs.mkdirSync(OUT, { recursive: true });

const clock = (d = new Date()) =>
  d.toTimeString().slice(0, 8) + "." + String(d.getMilliseconds()).padStart(3, "0");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const secs = (ms) => (ms / 1000).toFixed(1);
const report = [];
const checks = [];
function mark(message) {
  const line = `${clock()}  ${message}`;
  fs.appendFileSync(path.join(OUT, "timeline.txt"), line + "\r\n", "utf8");
  console.log(line);
}
function note(step, text) {
  report.push(`[${step}] ${text}`);
  mark(`   ${step}: ${text}`);
}
function check(step, label, ok, detail = "") {
  checks.push({ step, label, ok, detail });
  const line = `[${step}] ${ok ? "DAT     " : "KHONG DAT"} ${label}${detail ? " — " + detail : ""}`;
  report.push(line);
  mark(`   ${line}`);
  return ok;
}
async function get(p) {
  const r = await fetch(B + p);
  if (!r.ok) throw new Error(`${p}: ${r.status}`);
  return r.json();
}
const snapshot = () => get("/api/snapshot");
async function snap(name) {
  fs.writeFileSync(path.join(OUT, `trang-thai-${name}.json`), JSON.stringify(await snapshot(), null, 2), "utf8");
}
const node = (s, n) => s.simulator.nodes.find((x) => x.node_id === n);
const openFor = (s, table) => s.requests.filter((r) => r.table_id === table);
const patternOf = (x) => (x ? `${x.pattern}${x.pattern === "unconfirmed" ? "/" + x.phase : ""}` : "?");
async function events(params) {
  return (await get(`/api/event-log?limit=200&${params}`)).items;
}
async function until(predicate, timeout, step = 100) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try {
      if (await predicate()) return Date.now() - start;
    } catch {
      /* server may be restarting */
    }
    await sleep(step);
  }
  return null;
}
// Watch one simulated table for `ms`, recording each pattern change and the worst counts seen.
async function watch(n, ms, extra = async () => ({})) {
  const start = Date.now();
  const changes = [];
  let last = null;
  const seen = { maxOpen: 0, samples: [] };
  while (Date.now() - start < ms) {
    const s = await snapshot();
    const p = patternOf(node(s, n));
    if (p !== last) changes.push([Date.now() - start, p]);
    last = p;
    seen.maxOpen = Math.max(seen.maxOpen, openFor(s, n).length);
    seen.samples.push({ t: Date.now() - start, s, ...(await extra(s)) });
    await sleep(100);
  }
  seen.changes = changes;
  seen.text = changes.map(([t, p]) => `${secs(t)}s ${p}`).join(" → ");
  return seen;
}

// ------------------------------------------------------------------ server control
let server = null;
function startServer() {
  const log = fs.openSync(path.join(OUT, "server-log.txt"), "a");
  server = spawn(PY, ["tools/demo.py", "--mode", "simulation"], {
    cwd: ROOT,
    env: { ...process.env, PBL_DATA_DIR: "data-at07", PYTHONIOENCODING: "utf-8" },
    stdio: ["ignore", log, log],
    windowsHide: true,
  });
}
function killHard() {
  // Same as the guide: kill the process that owns port 8000 (like pulling the plug).
  execSync(
    `powershell -NoProfile -Command "$p=(Get-NetTCPConnection -LocalPort 8000 -State Listen).OwningProcess; Stop-Process -Id $p -Force"`,
  );
}

(async () => {
  fs.writeFileSync(path.join(OUT, "timeline.txt"), "", "utf8");
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 }, acceptDownloads: true });
  const page = await context.newPage();
  const staffContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const staff = await staffContext.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  staff.on("pageerror", (e) => errors.push(e.message));

  const shot = (name, p = page) => p.screenshot({ path: path.join(OUT, name), fullPage: true });
  const nav = async (name) => page.getByRole("button", { name, exact: true }).click();
  const selectTable = async (n) =>
    page.getByLabel("Chọn bàn").selectOption({ label: `Bàn ${String(n).padStart(2, "0")}` });
  const gateway = async (on) =>
    page.getByRole("button", { name: on ? "Kết nối lại gateway" : "Ngắt gateway mô phỏng" }).click();
  async function hold(category, ms = 5200) {
    const button = page.getByRole("button", {
      name: `${category === "SERVICE" ? "PHỤC VỤ" : "THANH TOÁN"} Giữ 5 giây`,
    });
    await button.focus();
    await page.keyboard.down("Space");
    await sleep(ms);
    await page.keyboard.up("Space");
    return Date.now();
  }
  const openCard = async (n) => {
    await nav("Tổng quan");
    await page.getByRole("button", { name: new RegExp(`^Bàn ${String(n).padStart(2, "0")} — `) }).click();
  };
  const closeDetail = () => page.getByLabel("Đóng chi tiết").click();

  // ------------------------------------------------------------------ 5.2 setup
  mark("Bat dau AT-07 (dien tap mo phong, tu dong bang Chrome/Playwright)");
  fs.rmSync(path.join(ROOT, "data-at07"), { recursive: true, force: true });
  startServer();
  check("0", "Server khởi động (data-at07)", (await until(() => get("/api/health"), 30000)) !== null);
  await page.goto(B);
  await page.getByRole("heading", { name: "Tổng quan tại quán" }).waitFor();
  await page.getByText("Trung tâm trực tuyến").waitFor({ timeout: 15000 });
  const idle = await page.getByRole("button", { name: /^Bàn \d+ — Bàn rảnh/ }).count();
  check("0", "Tổng quan có 24 bàn rảnh, trung tâm trực tuyến", idle === 24, `${idle} bàn rảnh`);
  await shot("AT07_0_ban-dau.png");
  execSync(
    `"${PY}" tools/backup.py backup --mode simulation --data-dir data-at07 --file evidence/AT-07/sao-luu-truoc.sqlite3`,
    { cwd: ROOT },
  );
  note("0", "Đã sao lưu sổ: sao-luu-truoc.sqlite3");
  await snap("truoc");
  await staff.goto(B + "/staff");

  // ------------------------------------------------------------------ 1a
  await nav("Bàn mô phỏng");
  await gateway(false);
  mark("1a ngat");
  await selectTable(1);
  const released1a = await hold("SERVICE");
  mark("1a tha nut");
  const w1a = await watch(1, 10000);
  note("1a", `Đèn bàn 01 sau khi thả: ${w1a.text}`);
  const unconfirmed = w1a.changes.find(([, p]) => p === "unconfirmed/registering");
  check("1a", "Trong 5 s sau khi thả có kết quả nhìn thấy (chưa xác nhận)", !!unconfirmed && unconfirmed[0] <= 5000,
    unconfirmed ? `“Chưa xác nhận được đăng ký” sau ${secs(unconfirmed[0])} s` : "không thấy");
  check("1a", "Không bao giờ đỏ sáng khi trung tâm chưa ghi", !w1a.changes.some(([, p]) => p === "red"));
  check("1a", "Không có yêu cầu nào khi đang ngắt", w1a.maxOpen === 0, `tối đa ${w1a.maxOpen}`);
  await shot("AT07_1a_chua-xac-nhan.png");
  await gateway(true);
  mark("1a noi lai");
  const t1aRed = await until(async () => patternOf(node(await snapshot(), 1)) === "red", 20000);
  const s1a = await snapshot();
  check("1a", "Nối lại → đỏ sáng, đúng 1 yêu cầu Bàn 01", t1aRed !== null && openFor(s1a, 1).length === 1,
    `đỏ sáng sau ${t1aRed === null ? "—" : secs(t1aRed)} s; ${openFor(s1a, 1).length} yêu cầu`);
  await shot("AT07_1a_noi-lai.png");

  // ------------------------------------------------------------------ 1b
  await selectTable(2);
  await page.getByLabel("Lỗi ở gói tiếp theo").selectOption("drop_receipt");
  await until(async () => (await snapshot()).simulator.fault === "drop_receipt", 3000);
  const armed = (await snapshot()).simulator;
  check("1b", "Lỗi được gắn cho Bàn 02", armed.fault === "drop_receipt" && armed.fault_node === 2,
    `fault=${armed.fault}, bàn=${armed.fault_node}`);
  await hold("BILL");
  mark("1b");
  const t1b = await until(async () => patternOf(node(await snapshot(), 2)) === "red", 25000);
  const s1b = await snapshot();
  const t2 = openFor(s1b, 2);
  const log2 = (await events("table_id=2")).map((e) => e.type).reverse();
  check("1b", "Bàn 02 tự gửi lại rồi đỏ sáng", t1b !== null, t1b === null ? "" : `sau ${secs(t1b)} s`);
  check("1b", "Chỉ 1 yêu cầu Bàn 02, loại Thanh toán", t2.length === 1 && t2[0].category === "BILL",
    `${t2.length} yêu cầu, ${t2[0]?.category}`);
  check("1b", "Nhật ký: REGISTERED rồi DUPLICATE", log2[0] === "REGISTERED" && log2.includes("DUPLICATE"), log2.join(", "));
  check("1b", "Lỗi giả lập chỉ dùng một lần", s1b.simulator.fault === "none", `fault = ${s1b.simulator.fault}`);
  await openCard(2);
  await shot("AT07_1b_chi-tiet.png");
  await closeDetail();

  // ------------------------------------------------------------------ 2a
  await openCard(1);
  await page.getByRole("button", { name: "Xác nhận yêu cầu", exact: true }).click();
  const tGreen = await until(() => page.getByText("Bàn báo đã hiển thị: đèn xanh").isVisible(), 20000);
  check("2a", "Trước khi ngắt: bàn báo đèn xanh", tGreen !== null);
  await closeDetail();
  await snap("2a-truoc-ngat");
  const before2a = await snapshot();
  await nav("Bàn mô phỏng");
  await selectTable(1);
  await gateway(false);
  const t0 = Date.now();
  mark("2a ngat");
  const tBanner = await until(() => page.getByText(/Gateway đang ngắt/).isVisible(), 10000);
  const timings = { banner: tBanner };
  let falseChange = null;
  await until(async () => {
    const s = await snapshot();
    const t = Date.now() - t0;
    const n1 = node(s, 1);
    const r1 = openFor(s, 1)[0];
    if (!r1 || r1.state !== "ACKNOWLEDGED") falseChange = `yêu cầu Bàn 01: ${r1 ? r1.state : "đã đóng"}`;
    if (n1.pattern === "off" || n1.pattern === "red") falseChange = `đèn Bàn 01: ${n1.pattern}`;
    if (timings.node === undefined && n1.pattern === "unconfirmed") timings.node = t;
    if (timings.log === undefined) {
      const f = await events("type=FAILURE&table_id=1");
      if (f.some((e) => (e.reason || "").includes("table_contact_lost"))) timings.log = Date.now() - t0;
    }
    return timings.node !== undefined && timings.log !== undefined;
  }, 30000);
  note("2a", `(a) dải Gateway đang ngắt: ${tBanner === null ? "không thấy" : secs(tBanner) + " s"}; (b) Bàn 01 “Mất liên lạc”: ${timings.node === undefined ? "không thấy" : secs(timings.node) + " s"}; (c) nhật ký table_contact_lost: ${timings.log === undefined ? "không thấy trong 30 s" : secs(timings.log) + " s"}`);
  check("2a", "(a) Dải “Gateway đang ngắt” hiện ngay", tBanner !== null && tBanner <= 2000, tBanner === null ? "" : `${secs(tBanner)} s`);
  check("2a", "(b) Bàn 01 hiện mất liên lạc trong 10 s", timings.node !== undefined && timings.node <= 10000,
    timings.node === undefined ? "" : `${secs(timings.node)} s`);
  check("2a", "(c) Nhật ký có table_contact_lost trong 10 s", timings.log !== undefined && timings.log <= 10000,
    timings.log === undefined ? "không thấy" : `${secs(timings.log)} s`);
  check("2a", "Bàn 01 giữ xanh, không yêu cầu nào bị đóng", falseChange === null, falseChange || "");
  await shot("AT07_2a_mat-lien-lac-ban.png");
  await nav("Lịch sử");
  await page.getByRole("tab", { name: "Nhật ký sự kiện" }).click();
  await sleep(800);
  await shot("AT07_2a_nhat-ky.png");
  await nav("Tổng quan");
  await shot("AT07_2a_tong-quan.png");
  await nav("Bàn mô phỏng");
  await selectTable(3);
  await hold("SERVICE");
  mark("2a ban 03 goi khi dang ngat");
  const w2a3 = await watch(3, 8000);
  const u3 = w2a3.changes.find(([, p]) => p === "unconfirmed/registering");
  check("2a", "Bàn 03 gọi khi đang ngắt → chưa xác nhận trong 5 s, không đỏ, không có yêu cầu",
    !!u3 && u3[0] <= 5000 && w2a3.maxOpen === 0 && !w2a3.changes.some(([, p]) => p === "red"),
    `${w2a3.text}; ${w2a3.maxOpen} yêu cầu`);
  await shot("AT07_2a_ban03.png");

  // ------------------------------------------------------------------ 2b
  await selectTable(2);
  const hidden = page.getByRole("button", { name: "Nút ẩn hoàn tất · bấm hai lần" });
  await hidden.click();
  await sleep(120);
  await hidden.click();
  mark("2b bam dup");
  const w2b = await watch(2, 10000);
  note("2b", `Đèn bàn 02: ${w2b.text}`);
  check("2b", "Khi đang ngắt: chờ trung tâm, không về “đèn tắt”",
    w2b.changes.some(([, p]) => p === "completing") && !w2b.changes.some(([, p]) => p === "off"));
  const stillOpen = w2b.samples.every((x) => openFor(x.s, 2).length === 1);
  check("2b", "Yêu cầu Bàn 02 vẫn mở suốt lúc ngắt", stillOpen);
  await shot("AT07_2b_cho.png");
  await gateway(true);
  mark("2b noi lai");
  const t2bOff = await until(async () => {
    const s = await snapshot();
    return patternOf(node(s, 2)) === "off" && openFor(s, 2).length === 0;
  }, 25000);
  const history2 = (await get("/api/history?table_id=2")).items;
  const completed2 = (await events("table_id=2&type=COMPLETED")).length;
  check("2b", "Nối lại → đèn tắt, Bàn 02 rời Tổng quan, lịch sử Hoàn tất, đóng đúng 1 lần",
    t2bOff !== null && history2[0]?.state === "COMPLETED" && completed2 === 1,
    `${t2bOff === null ? "không tắt" : "tắt sau " + secs(t2bOff) + " s"}; ${completed2} COMPLETED`);
  await shot("AT07_2b_xong.png");
  const t3reg = await until(async () => openFor(await snapshot(), 3).length === 1, 15000);
  note("2b", `Bàn 03 (gọi lúc đang ngắt) được ghi nhận sau khi nối lại: ${t3reg === null ? "không" : "có"}`);

  // ------------------------------------------------------------------ 2c
  await openCard(1);
  await page.getByLabel("Giao cho nhân viên", { exact: true }).selectOption("1");
  await closeDetail();
  const r1 = openFor(await snapshot(), 1)[0];
  const accept = staff.getByRole("button", { name: "Nhận việc", exact: true });
  const tTask = await until(async () => {
    await staff.getByRole("button", { name: "Kiểm tra cập nhật" }).click().catch(() => {});
    return accept.isVisible();
  }, 20000, 500);
  check("2c", "Máy nhân viên (Minh Anh) hiện việc Bàn 01 và nút Nhận việc", tTask !== null);
  await shot("AT07_2c_staff-co-viec.png", staff);
  await nav("Bàn mô phỏng");
  await gateway(false);
  mark("2c ngat");
  await accept.click();
  mark("2c bam nhan");
  const waitingText =
    (await until(() => staff.getByText("Đã bấm nhận · đang chờ trung tâm xác nhận.").isVisible(), 5000)) !== null;
  let acceptedEarly = false;
  await until(async () => {
    acceptedEarly ||= (await get(`/api/requests/${r1.id}`)).request.accepted_at !== null;
    return false;
  }, 10000, 250);
  check("2c", "Máy nhân viên hiện “Đã bấm nhận · đang chờ trung tâm xác nhận.”", waitingText);
  check("2c", "Trung tâm không tự coi là đã nhận khi đang ngắt (10 s)", !acceptedEarly);
  await shot("AT07_2c_staff-cho.png", staff);
  await openCard(1);
  check("2c", "Chi tiết Bàn 01 vẫn “Chờ nhân viên nhận”", await page.getByText("Chờ nhân viên nhận").first().isVisible());
  await shot("AT07_2c_quan-ly-cho.png");
  await closeDetail();
  await nav("Bàn mô phỏng");
  await gateway(true);
  mark("2c noi lai");
  const tAccepted = await until(async () => (await get(`/api/requests/${r1.id}`)).request.accepted_at !== null, 20000);
  check("2c", "Nối lại → trung tâm ghi nhận đã nhận", tAccepted !== null, tAccepted === null ? "" : `sau ${secs(tAccepted)} s`);
  await openCard(1);
  check("2c", "Quản lý thấy “Nhân viên đã nhận lúc …”",
    (await until(() => page.getByText(/Nhân viên đã nhận lúc/).isVisible(), 10000)) !== null);
  await shot("AT07_2c_da-nhan-quan-ly.png");
  await closeDetail();
  const guide = await until(() => staff.getByText("Đến bàn phục vụ và bấm đúp nút ẩn để hoàn tất.").isVisible(), 10000);
  const doneButtons = await staff.getByRole("button", { name: "Hoàn tất", exact: true }).count();
  check("2c", "Máy nhân viên hướng dẫn bấm đúp tại bàn, không có nút Hoàn tất", guide !== null && doneButtons === 0);
  await shot("AT07_2c_da-nhan-staff.png", staff);
  await nav("Bàn mô phỏng");
  await page.getByRole("button", { name: "Tắt nguồn thiết bị Quốc Bảo" }).click();
  mark("2c tat nguon thiet bi nhan vien 2");
  await openCard(3);
  await page.getByLabel("Giao cho nhân viên", { exact: true }).selectOption("2");
  const tDispatch = Date.now();
  await closeDetail();
  const tNotDelivered = await until(() => page.getByText(/Chưa tới thiết bị nhân viên/).first().isVisible(), 30000);
  check("2c", "Giao cho máy đang tắt → “Chưa tới thiết bị nhân viên”", tNotDelivered !== null,
    tNotDelivered === null ? "" : `sau ${secs(Date.now() - tDispatch)} s`);
  await shot("AT07_2c_chua-toi-thiet-bi.png");

  // ------------------------------------------------------------------ 3
  await snap("sau-noi-lai");
  const after3 = await snapshot();
  const key = (r) => `${r.id}|${r.seq}|${r.received_at}|${r.category}`;
  const kept = before2a.requests.filter((r) => r.table_id !== 2);
  check("3", "Sau nối lại: các yêu cầu cũ giữ nguyên mã, số thứ tự, giờ gọi, loại",
    kept.every((r) => after3.requests.some((x) => key(x) === key(r))), kept.map((r) => `Bàn ${r.table_id} #${r.seq}`).join(", "));
  const perTable = {};
  after3.requests.forEach((r) => (perTable[r.table_id] = (perTable[r.table_id] || 0) + 1));
  check("3", "Không bàn nào có 2 yêu cầu", Object.values(perTable).every((c) => c === 1), JSON.stringify(perTable));
  const seqs = after3.requests.map((r) => r.seq);
  check("3", "Hàng đợi vẫn theo số thứ tự tăng dần", seqs.every((v, i) => i === 0 || v > seqs[i - 1]), seqs.join(","));
  await nav("Bàn mô phỏng");
  await selectTable(2);
  await hold("SERVICE");
  mark("3 ban 02 goi lan moi");
  await until(async () => patternOf(node(await snapshot(), 2)) === "red", 20000);
  const new2 = openFor(await snapshot(), 2)[0];
  const old2 = before2a.requests.find((r) => r.table_id === 2);
  check("3", "Bàn 02 gọi lần mới → mã mới, số thứ tự mới",
    !!new2 && new2.id !== old2.id && new2.seq > Math.max(...seqs), new2 ? `#${old2.seq} → #${new2.seq}` : "không có");
  await nav("Tổng quan");
  await shot("AT07_3_sau-noi-lai.png");

  // ------------------------------------------------------------------ 4
  await nav("Bàn mô phỏng");
  await selectTable(1);
  const before4 = openFor(await snapshot(), 1)[0];
  const restartClick = Date.now();
  await page.getByRole("button", { name: "Khởi động lại nút (thay pin)" }).click();
  mark("4 khoi dong lai ban 01");
  const watcher = watch(1, 15000);
  await selectTable(4);
  await hold("BILL");
  mark("4 ban 04 goi");
  const w4 = await watcher;
  note("4", `Đèn bàn 01 sau khởi động lại: ${w4.text}`);
  const s4 = await snapshot();
  const after4 = openFor(s4, 1);
  const reconciled = (await events("type=RECONCILED&table_id=1")).filter(
    (e) => e.received_at * 1000 >= restartClick - 1000);
  note("4", `Nhật ký: ${reconciled.map((e) => `RECONCILED (${e.reason})`).join(", ") || "không có RECONCILED"}; ` +
    `trạng thái “đang đối soát” ${w4.changes.some(([, p]) => p.startsWith("reconciling")) ? "có" : "không"} bắt được ở nhịp lấy mẫu 0,1 s`);
  check("4", "Bàn 01 khởi động lại đã đối soát với trung tâm (RECONCILED, phiên mới)", reconciled.length === 1,
    reconciled[0]?.reason || "");
  check("4", "Bàn 01 về đúng yêu cầu cũ (cùng mã, loại, giờ), đèn xanh, không tạo cuộc gọi mới",
    after4.length === 1 && after4[0].id === before4.id && after4[0].received_at === before4.received_at &&
      after4[0].category === before4.category && patternOf(node(s4, 1)) === "green");
  check("4", "Bàn 04 gọi bình thường trong lúc đó", openFor(s4, 4).length === 1);
  await selectTable(1);
  await page.getByRole("button", { name: "Giả lập pin yếu" }).click();
  const tBattery = await until(async () => (await snapshot()).tables.find((t) => t.id === 1).battery_low === 1, 15000);
  check("4", "Pin yếu Bàn 01 hiện tại trung tâm", tBattery !== null);
  await nav("Tổng quan");
  await shot("AT07_4_sau-khoi-dong-lai.png");

  // ------------------------------------------------------------------ 5a
  const s5 = await snapshot();
  const states = s5.requests.map((r) => `Bàn ${r.table_id}: ${r.state}/${r.accepted_at ? "ACCEPTED" : r.delivered_at ? "DELIVERED" : r.staff_id ? "DISPATCHED" : "NONE"}`);
  note("5a", `Trước khi tắt: ${states.join("; ")}`);
  await snap("truoc-khi-tat");
  await shot("AT07_5a_truoc-khi-tat.png");
  const killAt = Date.now();
  mark("5a tat ngang");
  killHard();
  check("5a", "Server đã bị tắt ngang", (await until(async () => {
    try { await fetch(B + "/api/health"); return false; } catch { return true; }
  }, 10000)) !== null);
  startServer();
  mark("5a mo lai");
  const restartAt = Date.now();
  const tHealth = await until(() => get("/api/health"), 60000);
  let tUsable = null;
  if (tHealth !== null) {
    await page.reload();
    await page.getByRole("heading", { name: "Tổng quan tại quán" }).waitFor({ timeout: 30000 });
    await page.getByText("Trung tâm trực tuyến").waitFor({ timeout: 30000 });
    tUsable = Date.now() - restartAt;
  }
  await snap("sau-khi-tat");
  const health = await get("/api/health");
  fs.appendFileSync(path.join(OUT, "khoi-phuc.txt"), JSON.stringify(health.startup, null, 2) + "\r\n", "utf8");
  const s5b = await snapshot();
  const fields = ["id", "seq", "table_id", "category", "state", "received_at", "acknowledged_at", "staff_id", "delivered_at", "accepted_at", "version"];
  const pick = (r) => JSON.stringify(fields.map((f) => r[f]));
  const same = s5.requests.length === s5b.requests.length && s5.requests.every((r, i) => pick(r) === pick(s5b.requests[i]));
  note("5a", `Mở lại: API sẵn sàng sau ${secs(tHealth)} s, trang quản lý dùng lại được sau ${secs(tUsable)} s (tính từ lúc chạy lại lệnh); recovered_active = ${health.startup.recovered_active}, recovery_ms = ${health.startup.recovery_ms}`);
  check("5a", "Mọi yêu cầu quay lại đủ, đúng mã/số/giờ/trạng thái, không trùng, không đóng nhầm", same,
    `${s5.requests.length} trước / ${s5b.requests.length} sau`);
  const starts = await events("type=CENTRE_START");
  check("5a", "Nhật ký có “Trung tâm khởi động” sau lần mở lại", starts.some((e) => e.received_at * 1000 >= killAt - 1000));
  await shot("AT07_5a_sau-khi-tat.png");

  // ------------------------------------------------------------------ 6
  await nav("Bàn mô phỏng");
  await page.getByRole("button", { name: "Tua +300 giây · chỉ đồng hồ demo" }).click();
  await until(async () => (await events("type=OVERDUE")).length > 0, 15000);
  await nav("Lịch sử");
  await page.getByRole("tab", { name: "Nhật ký sự kiện" }).click();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "↓ Xuất CSV sự kiện" }).click(),
  ]);
  const csvPath = path.join(OUT, "pbl4-events.csv");
  await download.saveAs(csvPath);
  await shot("AT07_6_nhat-ky.png");
  mark("6 xuat CSV");
  const text = fs.readFileSync(csvPath, "utf8").replace(/^\uFEFF/, "");
  const [header, ...rows] = text.trim().split(/\r?\n/);
  const columns = header.split(",");
  const typeIndex = columns.indexOf("event");
  const counts = {};
  rows.forEach((row) => {
    const type = row.split(",")[typeIndex];
    counts[type] = (counts[type] || 0) + 1;
  });
  const eight = ["REGISTERED", "ACKNOWLEDGED", "DISPATCHED", "ACCEPTED", "OVERDUE", "COMPLETED", "DUPLICATE", "FAILURE"];
  note("6", `Cột CSV: ${columns.join(", ")}`);
  note("6", `Số dòng mỗi loại: ${Object.entries(counts).map(([k, v]) => `${k}=${v}`).join(", ")}`);
  check("6", "Đủ 8 loại sự kiện", eight.every((t) => counts[t] > 0), eight.filter((t) => !counts[t]).join(", ") || "đủ");
  check("6", "Giờ theo ISO 8601 +07:00", rows.every((r) => /\+07:00/.test(r.split(",")[1])));
  const epochIndex = columns.indexOf("epoch");
  check("6", "Còn các dòng từ trước lần tắt ngang", rows.some((r) => Number(r.split(",")[epochIndex]) * 1000 < killAt));
  check("6", "Không có cột thông tin khách", !columns.some((c) => /guest|customer|phone|khach/i.test(c)));

  // ------------------------------------------------------------------ 5.4 cleanup
  await nav("Bàn mô phỏng");
  const sim = (await snapshot()).simulator;
  if (sim.fault !== "none") await page.getByLabel("Lỗi ở gói tiếp theo").selectOption("none");
  if (!(await snapshot()).gateway.connected) await gateway(true);
  const on = page.getByRole("button", { name: /^Bật nguồn thiết bị/ });
  while ((await on.count()) > 0) await on.first().click();
  await selectTable(1);
  const unbattery = page.getByRole("button", { name: "Bỏ giả lập pin yếu" });
  if (await unbattery.count()) await unbattery.click();
  await snap("ket-thuc");
  execSync(
    `"${PY}" tools/backup.py backup --mode simulation --data-dir data-at07 --file evidence/AT-07/so-sau-cung.sqlite3`,
    { cwd: ROOT },
  );
  mark("Ket thuc AT-07");
  check("chung", "Không có lỗi JavaScript trên trang", errors.length === 0, errors.join(" | "));
  await browser.close();
  killHard();

  const passed = checks.filter((c) => c.ok).length;
  const summary = [
    "AT-07 — dien tap mo phong (simulation rehearsal), chay tu dong bang Chrome + Playwright",
    `Thoi gian: ${new Date().toString()}`,
    `Ket qua kiem tra phan mem: ${passed}/${checks.length} dat`,
    "",
    ...report,
  ];
  fs.writeFileSync(path.join(OUT, "ket-qua-do.txt"), summary.join("\r\n") + "\r\n", "utf8");
  console.log(`\n${passed}/${checks.length} checks passed`);
  checks.filter((c) => !c.ok).forEach((c) => console.log("FAILED:", c.step, c.label, c.detail));
})().catch((e) => {
  console.error(e);
  try { killHard(); } catch {}
  process.exit(1);
});
