import { test, expect } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  const r = await request.post("/api/sim/action", {
    data: { action: "reset", confirm: "RESET DEMO" },
  });
  expect(r.ok()).toBeTruthy();
});

test("desktop full CALL → ACK → ASSIGN → ACCEPT → physical-sim DONE", async ({
  page,
  context,
}) => {
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
  const call = page.getByRole("button", { name: "GIỮ ĐỂ GỌI 5 giây liên tục" });
  await call.focus();
  await page.keyboard.down("Space");
  await page.waitForTimeout(200);
  await page.keyboard.up("Space");
  await expect(page.getByText("Đang ngủ · LED tắt")).toBeVisible();
  await call.focus();
  await page.keyboard.down("Space");
  await page.waitForTimeout(5200);
  await page.keyboard.up("Space");
  await expect(page.getByText("Trung tâm đã lưu · LED đỏ")).toBeVisible();
  await page.getByRole("button", { name: "Tổng quan", exact: true }).click();
  await page.getByRole("button", { name: "Bàn 01 — Chờ xác nhận" }).click();
  await page
    .getByRole("button", { name: "Xác nhận yêu cầu", exact: true })
    .click();
  await expect(
    page.getByText("Đang chờ bàn nhận", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Giao cho nhân viên", { exact: true })
    .selectOption("1");
  const staff = await context.newPage();
  await staff.setViewportSize({ width: 390, height: 844 });
  await staff.goto("/staff");
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
  await expect(
    page.getByRole("button", { name: "Bàn 01 — Đang phục vụ" }),
  ).toBeVisible();
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
  const hidden = page.getByRole("button", {
    name: "Nút ẩn · bấm hai lần để hoàn tất",
  });
  await hidden.click();
  await page.waitForTimeout(120);
  await hidden.click();
  await expect(page.getByText("Đang ngủ · LED tắt")).toBeVisible();
  await staff.reload();
  await expect(staff.getByText("Chưa có việc được giao")).toBeVisible();
  await page.getByRole("button", { name: "Lịch sử", exact: true }).click();
  await expect(
    page.locator("tbody").getByRole("cell", { name: "Hoàn tất", exact: true }),
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
  await page.getByRole("button", { name: "Bàn mô phỏng", exact: true }).click();
  await page.getByRole("button", { name: "Gọi đồng thời 4 bàn" }).click();
  await page
    .getByRole("button", { name: "Tua +301 giây · chỉ clock demo" })
    .click();
  await page.getByRole("button", { name: "Ngắt gateway mô phỏng" }).click();
  await expect(page.getByText(/Gateway đang ngắt/)).toBeVisible();
  await page.getByRole("button", { name: "Kết nối lại gateway" }).click();
  await page.context().setOffline(true);
  await page.waitForTimeout(1500);
  await page.context().setOffline(false);
  await page.getByRole("button", { name: "Tổng quan", exact: true }).click();
  await expect(page.getByRole("button", { name: /Quá 5 phút 4/ })).toBeVisible({
    timeout: 15000,
  });
  await expect(page.getByText("Trung tâm trực tuyến")).toBeVisible({
    timeout: 15000,
  });
  const before = streams;
  await page.waitForTimeout(2500);
  expect(streams).toBe(before);
  expect(streams).toBeLessThanOrEqual(3);
});

test("staff inbox recovers from API error with retry", async ({
  page,
  request,
}) => {
  await request.post("/api/sim/action", { data: { action: "burst" } });
  const snapshot = await (await request.get("/api/snapshot")).json();
  const r = snapshot.requests[0];
  const ack = await request.post(`/api/requests/${r.id}/ack`, {
    data: { expected_version: r.version, idempotency_key: crypto.randomUUID() },
  });
  const acknowledged = await ack.json();
  await request.post(`/api/requests/${r.id}/assign`, {
    data: {
      expected_version: acknowledged.version,
      idempotency_key: crypto.randomUUID(),
      staff_id: 1,
    },
  });
  await page.route("**/api/staff/1/inbox", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Tạm ngắt hộp công việc" }),
    }),
  );
  await page.goto("/staff");
  await expect(page.getByRole("alert")).toContainText("Tạm ngắt hộp công việc");
  await page.unroute("**/api/staff/1/inbox");
  await page.getByRole("button", { name: "Kiểm tra cập nhật" }).click();
  await expect(
    page.getByRole("button", { name: "Nhận việc", exact: true }),
  ).toBeVisible();
});
