import { test, expect } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  const r = await request.post("/api/sim/action", {
    data: { action: "reset", confirm: "RESET DEMO" },
  });
  expect(r.ok()).toBeTruthy();
});

test("desktop Bill call → ACK → dispatch → staff accept → double press at table", async ({
  page,
  context,
}) => {
  test.setTimeout(60000);
  await page.setViewportSize({ width: 1366, height: 768 });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Tổng quan tại quán" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Bàn \d+ — Bàn rảnh/ }),
  ).toHaveCount(24);
  await page.getByRole("button", { name: "Bàn mô phỏng", exact: true }).click();
  const bill = page.getByRole("button", { name: "THANH TOÁN Giữ 5 giây" });
  await bill.focus();
  await page.keyboard.down("Space");
  await page.waitForTimeout(200);
  await page.keyboard.up("Space");
  await expect(page.getByText("Đang ngủ · đèn tắt")).toBeVisible();
  await bill.focus();
  await page.keyboard.down("Space");
  await page.waitForTimeout(5200);
  await page.keyboard.up("Space");
  await expect(
    page.getByText("Trung tâm đã ghi nhận · đèn đỏ sáng"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Tổng quan", exact: true }).click();
  await page
    .getByRole("button", { name: "Bàn 01 — Thanh toán · Chờ xác nhận" })
    .click();
  await page
    .getByRole("button", { name: "Xác nhận yêu cầu", exact: true })
    .click();
  // Manager acknowledged is not the same as the table showing green: it follows a poll.
  await expect(page.getByText("Bàn báo đã hiển thị: đèn xanh")).toBeVisible({
    timeout: 10000,
  });
  await page
    .getByLabel("Giao cho nhân viên", { exact: true })
    .selectOption("1");
  const staff = await context.newPage();
  await staff.setViewportSize({ width: 390, height: 844 });
  await staff.goto("/staff");
  await expect(staff.getByText("Thanh toán", { exact: true })).toBeVisible({
    timeout: 10000,
  });
  await staff.getByRole("button", { name: "Nhận việc", exact: true }).click();
  await expect(
    staff.getByText("Đến bàn phục vụ và bấm đúp nút ẩn để hoàn tất."),
  ).toBeVisible();
  await expect(
    staff.getByRole("button", { name: "Hoàn tất", exact: true }),
  ).toHaveCount(0);
  expect(
    await staff.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await staff.screenshot({
    path: "../docs/screenshots/staff.png",
    fullPage: true,
  });
  await expect(page.getByText(/Nhân viên đã nhận lúc/)).toBeVisible({
    timeout: 10000,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.getByLabel("Đóng chi tiết").click();
  await page.screenshot({
    path: "../docs/screenshots/dashboard.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Bàn mô phỏng", exact: true }).click();
  await expect(
    page.getByText("Quản lý đã xác nhận · đèn xanh sáng"),
  ).toBeVisible();
  const hidden = page.getByRole("button", {
    name: "Nút ẩn hoàn tất · bấm hai lần",
  });
  await hidden.click();
  await page.waitForTimeout(120);
  await hidden.click();
  await expect(page.getByText("Đang ngủ · đèn tắt")).toBeVisible();
  await expect(staff.getByText("Chưa có việc được giao")).toBeVisible({
    timeout: 10000,
  });
  await page.getByRole("button", { name: "Lịch sử", exact: true }).click();
  await expect(
    page.locator("tbody").getByRole("cell", { name: "Hoàn tất", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Nhật ký sự kiện" }).click();
  await expect(
    page.locator("tbody").getByText("Hoàn tất tại bàn"),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("SSE reconnect snapshot, one subscription, reminder and gateway fault", async ({
  page,
}) => {
  let streams = 0;
  page.on("request", (r) => {
    if (r.url().endsWith("/api/events")) streams++;
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Tổng quan tại quán" }),
  ).toBeVisible();
  // An open event log must show new events by itself (AT-07 row 2a reads it live).
  await page.getByRole("button", { name: "Lịch sử", exact: true }).click();
  await page.getByRole("tab", { name: "Nhật ký sự kiện" }).click();
  await expect(
    page.getByRole("tab", { name: "Nhật ký sự kiện" }),
  ).toHaveAttribute("aria-selected", "true");
  await page.waitForTimeout(500); // initial list loaded before the new events arrive
  await page.request.post("/api/sim/action", { data: { action: "burst" } });
  await expect(
    page.locator("tbody").getByText("Trung tâm ghi nhận yêu cầu"),
  ).toHaveCount(4, { timeout: 5000 });
  await page.getByRole("button", { name: "Bàn mô phỏng", exact: true }).click();
  await page
    .getByRole("button", { name: "Tua +300 giây · chỉ đồng hồ demo" })
    .click();
  await page.getByRole("button", { name: "Ngắt gateway mô phỏng" }).click();
  await expect(page.getByText(/Gateway đang ngắt/)).toBeVisible();
  await page.getByRole("button", { name: "Kết nối lại gateway" }).click();
  await page.context().setOffline(true);
  await page.waitForTimeout(1500);
  await page.context().setOffline(false);
  await page.getByRole("button", { name: "Tổng quan", exact: true }).click();
  // Exactly 300 s after registration counts as overdue (≥ 300 s).
  await expect(page.getByRole("button", { name: /Quá 5 phút 4/ })).toBeVisible({
    timeout: 15000,
  });
  await expect(page.getByText(/Nhắc: 4 yêu cầu/)).toBeVisible();
  await expect(page.getByText("Trung tâm trực tuyến")).toBeVisible({
    timeout: 15000,
  });
  const before = streams;
  await page.waitForTimeout(2500);
  expect(streams).toBe(before);
  expect(streams).toBeLessThanOrEqual(3);
});

test("staff device screen recovers from API error; undelivered dispatch stays visible", async ({
  page,
  request,
}) => {
  test.setTimeout(60000);
  await request.post("/api/sim/action", { data: { action: "burst" } });
  await request.post("/api/sim/action", {
    data: { action: "staff_power", staff_id: 2, enabled: false },
  });
  const snapshot = await (await request.get("/api/snapshot")).json();
  const dispatch = (index: number, staff_id: number) =>
    request.post(`/api/requests/${snapshot.requests[index].id}/dispatch`, {
      data: {
        expected_version: snapshot.requests[index].version,
        idempotency_key: crypto.randomUUID(),
        staff_id,
      },
    });
  expect((await dispatch(0, 1)).ok()).toBeTruthy();
  expect((await dispatch(1, 2)).ok()).toBeTruthy();
  await page.route("**/api/staff-device/1", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Tạm ngắt thiết bị" }),
    }),
  );
  await page.goto("/staff");
  await expect(page.getByRole("alert")).toContainText("Tạm ngắt thiết bị");
  await page.unroute("**/api/staff-device/1");
  await page.getByRole("button", { name: "Kiểm tra cập nhật" }).click();
  await expect(
    page.getByRole("button", { name: "Nhận việc", exact: true }),
  ).toBeVisible({ timeout: 10000 });
  // The device of staff 2 is off: the dispatch must remain visibly unresolved (ER-P05).
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: /Bàn 02 · Chưa tới thiết bị nhân viên/ }),
  ).toBeVisible({ timeout: 20000 });
});
