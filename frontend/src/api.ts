import { z } from "zod";
import { useCallback, useEffect, useRef, useState } from "react";

export const requestSchema = z.object({
  id: z.string(),
  table_id: z.number(),
  state: z.enum([
    "WAITING_ACK",
    "ACKNOWLEDGED",
    "ASSIGNED",
    "ACCEPTED",
    "COMPLETED",
  ]),
  received_at: z.number(),
  acknowledged_at: z.number().nullable(),
  staff_id: z.number().nullable(),
  assignment_revision: z.number(),
  accepted_at: z.number().nullable(),
  completed_at: z.number().nullable(),
  reminded_at: z.number().nullable(),
  version: z.number(),
  closed_from: z.string().nullable(),
});
const tableSchema = z.object({
  id: z.number(),
  node_id: z.number(),
  name: z.string(),
  enabled: z.number(),
  last_seen: z.number().nullable(),
  led: z.string().nullable(),
  battery_mv: z.number().nullable(),
  observed_request_id: z.string().nullable(),
  observed_revision: z.number().nullable(),
});
const staffSchema = z.object({
  id: z.number(),
  name: z.string(),
  active: z.number(),
  available: z.number(),
});
const nodeSchema = z.object({
  node_id: z.number(),
  led: z.string(),
  phase: z.string(),
  hold_at: z.number().nullable(),
  request_id: z.string().nullable(),
  pending: z.string().nullable(),
  error: z.string().optional(),
});
export const snapshotSchema = z.object({
  mode: z.enum(["simulation", "hardware"]),
  tables: z.array(tableSchema),
  staff: z.array(staffSchema),
  requests: z.array(requestSchema),
  now: z.number(),
  gateway: z.object({ connected: z.boolean(), error: z.string().nullable() }),
  stats: z.object({
    completed: z.number(),
    average_seconds: z.number().nullable(),
  }),
  simulator: z
    .object({
      nodes: z.array(nodeSchema),
      connected: z.boolean(),
      poll_seconds: z.number(),
      double_ms: z.number(),
      fault: z.string(),
      delay: z.number(),
    })
    .nullable(),
});
export const detailSchema = z.object({
  request: requestSchema,
  events: z.array(
    z.object({
      id: z.number(),
      type: z.string(),
      received_at: z.number(),
      result: z.string(),
      reason: z.string().nullable(),
      actor: z.string().nullable(),
    }),
  ),
  assignments: z.array(
    z.object({
      revision: z.number(),
      staff_id: z.number(),
      delivered_at: z.number().nullable(),
      accepted_at: z.number().nullable(),
      revoked_at: z.number().nullable(),
    }),
  ),
  commands: z.array(
    z.object({
      command_id: z.string(),
      type: z.string(),
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
export type ServiceRequest = z.infer<typeof requestSchema>;
export type Snapshot = z.infer<typeof snapshotSchema>;
export type Detail = z.infer<typeof detailSchema>;
export type History = z.infer<typeof historySchema>;
export type Table = z.infer<typeof tableSchema>;
export const labels: Record<ServiceRequest["state"], string> = {
  WAITING_ACK: "Chờ xác nhận",
  ACKNOWLEDGED: "Đã xác nhận",
  ASSIGNED: "Đã giao việc",
  ACCEPTED: "Đang phục vụ",
  COMPLETED: "Hoàn tất",
};

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
export function stamp(value: number | null) {
  return value === null
    ? "—"
    : new Date(value * 1000).toLocaleString("vi-VN", {
        timeZone: "Asia/Ho_Chi_Minh",
        hour12: false,
      });
}
export function duration(seconds: number) {
  const n = Math.max(0, Math.floor(seconds));
  return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
}
