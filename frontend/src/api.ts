import { z } from "zod";
import { useCallback, useEffect, useRef, useState } from "react";

export const categorySchema = z.enum(["SERVICE", "BILL"]);
const commandSchema = z
  .object({
    type: z.string(),
    status: z.string(),
    attempts: z.number(),
    error: z.string().nullable(),
    applied_at: z.number().nullable(),
  })
  .nullable();
export const requestSchema = z.object({
  id: z.string(),
  seq: z.number(),
  table_id: z.number(),
  category: categorySchema,
  state: z.enum(["REGISTERED", "ACKNOWLEDGED", "COMPLETED"]),
  received_at: z.number(),
  acknowledged_at: z.number().nullable(),
  staff_id: z.number().nullable(),
  assignment_revision: z.number(),
  dispatched_at: z.number().nullable(),
  delivered_at: z.number().nullable(),
  accepted_at: z.number().nullable(),
  completed_at: z.number().nullable(),
  reminded_at: z.number().nullable(),
  version: z.number(),
  led_revision: z.number(),
  led_changed_at: z.number(),
  closed_from: z.string().nullable(),
  table_command: commandSchema.optional(),
  staff_command: commandSchema.optional(),
});
const tableSchema = z.object({
  id: z.number(),
  node_id: z.number(),
  name: z.string(),
  enabled: z.number(),
  last_seen: z.number().nullable(),
  led: z.string().nullable(),
  battery_mv: z.number().nullable(),
  battery_low: z.number(),
  observed_request_id: z.string().nullable(),
  observed_revision: z.number().nullable(),
});
const staffSchema = z.object({
  id: z.number(),
  name: z.string(),
  active: z.number(),
  available: z.number(),
  device_id: z.number().nullable(),
  last_seen: z.number().nullable(),
  battery_mv: z.number().nullable(),
  battery_low: z.number(),
});
const limitsSchema = z.object({
  hold_seconds: z.number(),
  registration_seconds: z.number(),
  reminder_seconds: z.number(),
  unresolved_seconds: z.number(),
  table_contact_seconds: z.number(),
  staff_contact_seconds: z.number(),
  poll_seconds: z.number(),
  staff_poll_seconds: z.number(),
  retention_days: z.number(),
});
const nodeSchema = z.object({
  node_id: z.number(),
  phase: z.string(),
  pattern: z.enum([
    "off",
    "hold",
    "pending",
    "red",
    "green",
    "unconfirmed",
    "completing",
    "reconciling",
  ]),
  led: z.string(),
  category: categorySchema.nullable(),
  hold_at: z.number().nullable(),
  request_id: z.string().nullable(),
  pending: z.string().nullable(),
  press_armed: z.boolean(),
  battery_low: z.boolean(),
  error: z.string().nullable(),
});
export const deviceSchema = z.object({
  staff_id: z.number(),
  device_id: z.number(),
  powered: z.boolean(),
  source: z.string(),
  vibrating: z.boolean(),
  link_lost: z.boolean(),
  error: z.string().nullable(),
  tasks: z.array(
    z.object({
      request_id: z.string(),
      request_seq: z.number(),
      table_id: z.number(),
      table_name: z.string(),
      category: categorySchema,
      revision: z.number(),
      state: z.enum(["SHOWN", "ACCEPTING", "ACCEPTED"]),
      shown_at: z.number(),
    }),
  ),
});
export const snapshotSchema = z.object({
  mode: z.enum(["simulation", "hardware"]),
  venue_id: z.number(),
  tables: z.array(tableSchema),
  staff: z.array(staffSchema),
  requests: z.array(requestSchema),
  limits: limitsSchema,
  now: z.number(),
  gateway: z.object({ connected: z.boolean(), error: z.string().nullable() }),
  stats: z.object({
    completed: z.number(),
    average_seconds: z.number().nullable(),
  }),
  staff_stub: z.boolean(),
  generation: z.number().optional(),
  double_ms: z.number(),
  simulator: z
    .object({
      nodes: z.array(nodeSchema),
      staff_devices: z.array(deviceSchema),
      connected: z.boolean(),
      poll_seconds: z.number(),
      double_ms: z.number(),
      fault: z.string(),
      fault_node: z.number().nullable().optional(),
      delay: z.number(),
    })
    .nullable(),
});
const eventSchema = z.object({
  id: z.number(),
  type: z.string(),
  received_at: z.number(),
  reason: z.string().nullable(),
  actor: z.string().nullable(),
  source: z.string(),
  staff_name: z.string().nullable().optional(),
});
export const detailSchema = z.object({
  request: requestSchema,
  events: z.array(eventSchema),
  assignments: z.array(
    z.object({
      revision: z.number(),
      staff_id: z.number(),
      staff_name: z.string(),
      assigned_at: z.number(),
      delivered_at: z.number().nullable(),
      accepted_at: z.number().nullable(),
      revoked_at: z.number().nullable(),
      revoke_reason: z.string().nullable(),
    }),
  ),
  commands: z.array(
    z.object({
      command_id: z.string(),
      type: z.string(),
      channel: z.string(),
      status: z.string(),
      attempts: z.number(),
      error: z.string().nullable(),
    }),
  ),
});
export const historySchema = z.object({
  total: z.number(),
  items: z.array(
    requestSchema.extend({
      table_name: z.string(),
      staff_name: z.string().nullable(),
    }),
  ),
});
export const eventLogSchema = z.object({
  total: z.number(),
  items: z.array(
    eventSchema.extend({
      table_name: z.string().nullable(),
      category: categorySchema.nullable(),
      request_seq: z.number().nullable(),
      request_id: z.string().nullable(),
    }),
  ),
});
export type Category = z.infer<typeof categorySchema>;
export type ServiceRequest = z.infer<typeof requestSchema>;
export type Snapshot = z.infer<typeof snapshotSchema>;
export type Detail = z.infer<typeof detailSchema>;
export type History = z.infer<typeof historySchema>;
export type EventLog = z.infer<typeof eventLogSchema>;
export type Table = z.infer<typeof tableSchema>;
export type Staff = z.infer<typeof staffSchema>;
export type Limits = z.infer<typeof limitsSchema>;
export type SimNode = z.infer<typeof nodeSchema>;
export type Device = z.infer<typeof deviceSchema>;
export type Stage = "NONE" | "DISPATCHED" | "DELIVERED" | "ACCEPTED";

// Lifecycle that drives the table indication: red = registered, green = manager acknowledged.
export const labels: Record<ServiceRequest["state"], string> = {
  REGISTERED: "Chờ xác nhận",
  ACKNOWLEDGED: "Đã xác nhận",
  COMPLETED: "Hoàn tất",
};
export const categoryLabels: Record<Category, string> = {
  SERVICE: "Phục vụ",
  BILL: "Thanh toán",
};
// Dispatch is tracked separately from the lifecycle (it never changes the table light).
export const stageLabels: Record<Stage, string> = {
  NONE: "Chưa giao việc",
  DISPATCHED: "Đang gửi tới thiết bị",
  DELIVERED: "Chờ nhân viên nhận",
  ACCEPTED: "Nhân viên đã nhận",
};
export const eventLabels: Record<string, string> = {
  REGISTERED: "Trung tâm ghi nhận yêu cầu",
  ACKNOWLEDGED: "Quản lý xác nhận",
  DISPATCHED: "Giao việc tới thiết bị nhân viên",
  DELIVERED: "Thiết bị nhân viên đã hiển thị",
  ACCEPTED: "Nhân viên nhận việc",
  OVERDUE: "Quá 5 phút chưa hoàn tất",
  COMPLETED: "Hoàn tất tại bàn",
  DUPLICATE: "Gói lặp đã bỏ qua",
  FAILURE: "Lỗi / chưa giải quyết",
  DISPATCH_CANCELLED: "Thu hồi giao việc",
  RECONCILED: "Nút bàn đối soát sau khởi động",
  BATTERY_LOW: "Cảnh báo pin yếu",
  CONFIG: "Thay đổi cấu hình",
  CENTRE_START: "Trung tâm khởi động",
  GATEWAY_CONNECTED: "Gateway đã kết nối",
};
const reasonLabels: [RegExp, string][] = [
  [/table_state_not_applied/, "Bàn chưa xác nhận trạng thái đèn sau 10 giây"],
  [/table_contact_lost/, "Mất liên lạc với bàn đang có yêu cầu"],
  [/dispatch_not_delivered/, "Lệnh giao việc chưa tới thiết bị sau 10 giây"],
  [/staff_device_contact_lost/, "Thiết bị nhân viên mất liên lạc"],
  [/command_expired/, "Lệnh hết hạn mà chưa được xác nhận"],
  [/command_failed/, "Lệnh đã thử 5 lần mà chưa được xác nhận"],
  [/wrong_venue/, "Gói tin của quán khác, đã từ chối"],
  [/unknown_node|unknown_staff_device/, "Thiết bị chưa đăng ký"],
  [/disabled_node/, "Bàn đã tắt sử dụng"],
  [/stale_assignment/, "Nhận việc từ phiên giao đã cũ"],
  [/stale_device_status/, "Trạng thái đèn cũ, đã bỏ qua"],
  [/no_request_for_correlation/, "Không có yêu cầu tương ứng"],
  [/gateway_disconnected/, "Gateway mất kết nối"],
  [/gateway_malformed_frame/, "Gateway gửi gói sai định dạng"],
  [/registration_retry/, "Bàn gửi lại yêu cầu đã ghi nhận"],
  [/active_request_exists/, "Bàn đã có yêu cầu đang mở"],
  [/completion_retry/, "Bàn gửi lại báo hoàn tất"],
  [/acceptance_retry/, "Thiết bị gửi lại xác nhận nhận việc"],
];
export function reasonText(reason: string | null) {
  if (!reason) return "";
  const known = reasonLabels.find(([pattern]) => pattern.test(reason));
  return known ? `${known[1]} (${reason})` : reason;
}

export function stage(r: ServiceRequest): Stage {
  if (r.staff_id === null) return "NONE";
  if (r.accepted_at !== null) return "ACCEPTED";
  if (r.delivered_at !== null) return "DELIVERED";
  return "DISPATCHED";
}
/** The table node itself confirmed the current indication (not inferred from any ACK). */
export function tableApplied(table: Table | undefined, r: ServiceRequest) {
  return (
    !!table &&
    table.observed_request_id === r.id &&
    table.observed_revision === r.led_revision
  );
}
export function isOverdue(r: ServiceRequest, now: number, limits: Limits) {
  return (
    r.completed_at === null && now - r.received_at >= limits.reminder_seconds
  );
}
export type Issue = { key: string; text: string };
/** Unresolved conditions the centre can observe for one active request. */
export function requestIssues(
  r: ServiceRequest,
  table: Table | undefined,
  staff: Staff | undefined,
  now: number,
  limits: Limits,
): Issue[] {
  const found: Issue[] = [];
  if (r.state === "COMPLETED") return found;
  if (
    !tableApplied(table, r) &&
    now - r.led_changed_at > limits.table_contact_seconds
  )
    found.push({
      key: "sync",
      text:
        r.state === "REGISTERED"
          ? "Bàn chưa xác nhận đã nhận đăng ký"
          : "Đèn xanh chưa tới bàn",
    });
  if (
    table &&
    table.last_seen !== null &&
    now - table.last_seen > limits.table_contact_seconds
  )
    found.push({ key: "contact", text: "Mất liên lạc với bàn" });
  if (
    r.table_command &&
    (r.table_command.status === "failed" ||
      r.table_command.status === "expired")
  )
    found.push({ key: "command", text: "Lệnh xuống bàn chưa được xác nhận" });
  if (r.staff_id !== null) {
    if (
      r.delivered_at === null &&
      r.dispatched_at !== null &&
      now - r.dispatched_at > limits.staff_contact_seconds
    )
      found.push({ key: "delivery", text: "Chưa tới thiết bị nhân viên" });
    if (
      staff &&
      staff.last_seen !== null &&
      now - staff.last_seen > limits.staff_contact_seconds
    )
      found.push({ key: "staff", text: "Thiết bị nhân viên mất liên lạc" });
  }
  return found;
}

export async function api(
  path: string,
  body?: unknown,
  headers: Record<string, string> = {},
): Promise<unknown> {
  const response = await fetch("/api" + path, {
    signal: AbortSignal.timeout(10000),
    method: body === undefined ? "GET" : "POST",
    headers: {
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      ...headers,
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const data: unknown = await response.json();
  if (!response.ok) {
    const error = z.object({ detail: z.unknown() }).safeParse(data);
    throw new Error(
      error.success && typeof error.data.detail === "string"
        ? error.data.detail
        : `Không thể xử lý (${response.status}). Kiểm tra dữ liệu và thử lại.`,
    );
  }
  return data;
}

export function message(e: unknown) {
  return e instanceof z.ZodError
    ? "Dữ liệu trung tâm không đúng định dạng. Thử tải lại."
    : e instanceof Error
      ? e.message
      : "Không thể thực hiện. Vui lòng thử lại.";
}

export function useLive() {
  const [data, setData] = useState<Snapshot | null>(null),
    [error, setError] = useState(""),
    [connected, setConnected] = useState(false);
  const busy = useRef(false),
    dirty = useRef(false),
    alive = useRef(true);
  const refresh = useCallback(async (): Promise<void> => {
    if (busy.current) {
      dirty.current = true;
      return;
    }
    busy.current = true;
    try {
      const value = snapshotSchema.parse(await api("/snapshot"));
      if (alive.current) {
        setData(value);
        setError("");
      }
    } catch (e) {
      if (alive.current)
        setError(
          e instanceof Error ? e.message : "Không kết nối được trung tâm",
        );
    } finally {
      busy.current = false;
      if (dirty.current && alive.current) {
        dirty.current = false;
        void refresh();
      }
    }
  }, []);
  useEffect(() => {
    alive.current = true;
    let source: EventSource | undefined,
      timer: ReturnType<typeof setTimeout> | undefined,
      stopped = false,
      delay = 1000;
    const connect = () => {
      if (stopped) return;
      source = new EventSource("/api/events");
      source.addEventListener("snapshot", () => {
        setConnected(true);
        delay = 1000;
        void refresh();
      });
      source.onerror = () => {
        setConnected(false);
        source?.close();
        if (!stopped) {
          timer = setTimeout(connect, delay);
          delay = Math.min(delay * 2, 16000);
        }
      };
    };
    void refresh();
    connect();
    return () => {
      alive.current = false;
      stopped = true;
      source?.close();
      clearTimeout(timer);
    };
  }, [refresh]);
  return { data, error, connected, refresh };
}

/** Central clock extrapolated locally; refreshed once per second (ER-P03). */
/**
 * Centre time for waiting ages (UT-12: refreshed at least once per second, never skipping).
 * One stable offset to the browser clock is kept: re-basing on every snapshot let network
 * jitter stall or skip a second. Only a real clock change (demo time travel) moves it.
 */
export function useNow(serverNow: number | undefined) {
  const offset = useRef(0);
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (serverNow === undefined) return;
    const measured = serverNow - Date.now() / 1000;
    if (Math.abs(measured - offset.current) > 1) {
      offset.current = measured;
      setNow(Date.now() / 1000 + measured);
    }
  }, [serverNow]);
  useEffect(() => {
    const timer = setInterval(
      () => setNow(Date.now() / 1000 + offset.current),
      250,
    );
    return () => clearInterval(timer);
  }, []);
  return now;
}

export function stamp(value: number | null) {
  return value === null
    ? "—"
    : new Date(value * 1000).toLocaleString("vi-VN", {
        timeZone: "Asia/Ho_Chi_Minh",
        hour12: false,
      });
}
export function clock(value: number | null) {
  return value === null
    ? "—"
    : new Date(value * 1000).toLocaleTimeString("vi-VN", {
        timeZone: "Asia/Ho_Chi_Minh",
        hour12: false,
      });
}
export function duration(seconds: number) {
  const n = Math.max(0, Math.floor(seconds));
  return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
}
