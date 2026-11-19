import { useCallback, useEffect, useState } from "react";
import {
  api,
  categoryLabels,
  duration,
  eventLabels,
  eventLogSchema,
  historySchema,
  labels,
  message,
  reasonText,
  stamp,
  type EventLog,
  type History,
  type Snapshot,
} from "./api";

const PAGE = 20;
const sourceLabels: Record<string, string> = {
  gateway: "Gateway",
  simulator: "Mô phỏng",
  stub: "Stub",
  web: "Quản lý",
  worker: "Trung tâm",
  system: "Hệ thống",
};

function epoch(local: string) {
  return String(new Date(local + "+07:00").getTime() / 1000);
}

export function HistoryPage({
  data,
  onDetail,
}: {
  data: Snapshot;
  onDetail: (id: string) => void;
}) {
  const [tab, setTab] = useState<"requests" | "events">("requests");
  return (
    <>
      <div className="section-heading">
        <div>
          <span className="eyebrow">DỮ LIỆU TỪ TRUNG TÂM</span>
          <h2>Lịch sử phục vụ</h2>
          <p>
            Lưu qua các lần khởi động. Nhật ký sự kiện giữ ít nhất{" "}
            {data.limits.retention_days} ngày, không chứa thông tin khách.
          </p>
        </div>
      </div>
      <div className="tabs" role="tablist">
        <button
          role="tab"
          aria-selected={tab === "requests"}
          className={tab === "requests" ? "tab current" : "tab"}
          onClick={() => setTab("requests")}
        >
          Yêu cầu
        </button>
        <button
          role="tab"
          aria-selected={tab === "events"}
          className={tab === "events" ? "tab current" : "tab"}
          onClick={() => setTab("events")}
        >
          Nhật ký sự kiện
        </button>
      </div>
      {tab === "requests" ? (
        <RequestHistory data={data} onDetail={onDetail} />
      ) : (
        <EventHistory data={data} onDetail={onDetail} />
      )}
    </>
  );
}

function Pagination({
  offset,
  shown,
  total,
  unit,
  setOffset,
}: {
  offset: number;
  shown: number;
  total: number;
  unit: string;
  setOffset: (value: number) => void;
}) {
  return (
    <div className="pagination">
      <span>
        {offset + 1}–{offset + shown} / {total} {unit}
      </span>
      <button
        disabled={!offset}
        onClick={() => setOffset(Math.max(0, offset - PAGE))}
      >
        Trước
      </button>
      <button
        disabled={offset + PAGE >= total}
        onClick={() => setOffset(offset + PAGE)}
      >
        Sau
      </button>
    </div>
  );
}

function RequestHistory({
  data,
  onDetail,
}: {
  data: Snapshot;
  onDetail: (id: string) => void;
}) {
  const [history, setHistory] = useState<History | null>(null),
    [error, setError] = useState(""),
    [table, setTable] = useState(""),
    [category, setCategory] = useState(""),
    [staff, setStaff] = useState(""),
    [state, setState] = useState(""),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [offset, setOffset] = useState(0);
  const params = new URLSearchParams({
    limit: String(PAGE),
    offset: String(offset),
  });
  if (table) params.set("table_id", table);
  if (category) params.set("category", category);
  if (staff) params.set("staff_id", staff);
  if (state) params.set("state", state);
  if (start) params.set("start", epoch(start));
  if (end) params.set("end", epoch(end));
  const query = params.toString();
  const load = useCallback(async () => {
    setError("");
    try {
      setHistory(historySchema.parse(await api("/history?" + query)));
    } catch (e) {
      setError(message(e));
    }
  }, [query]);
  // A new filter shows the loading state; new data at the centre refreshes in place.
  useEffect(() => setHistory(null), [query]);
  useEffect(() => {
    void load();
  }, [load, data.generation]);
  const change = (set: (value: string) => void) => (value: string) => {
    set(value);
    setOffset(0);
  };
  return (
    <>
      <div className="history-filters">
        <label>
          Bàn
          <select
            value={table}
            onChange={(e) => change(setTable)(e.target.value)}
          >
            <option value="">Tất cả</option>
            {data.tables.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Loại yêu cầu
          <select
            value={category}
            onChange={(e) => change(setCategory)(e.target.value)}
          >
            <option value="">Tất cả</option>
            {Object.entries(categoryLabels).map(([key, name]) => (
              <option key={key} value={key}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Nhân viên
          <select
            value={staff}
            onChange={(e) => change(setStaff)(e.target.value)}
          >
            <option value="">Tất cả</option>
            {data.staff.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Trạng thái
          <select
            value={state}
            onChange={(e) => change(setState)(e.target.value)}
          >
            <option value="">Tất cả</option>
            {Object.entries(labels).map(([key, name]) => (
              <option key={key} value={key}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Từ thời gian (VN)
          <input
            type="datetime-local"
            value={start}
            onChange={(e) => change(setStart)(e.target.value)}
          />
        </label>
        <label>
          Đến thời gian (VN)
          <input
            type="datetime-local"
            value={end}
            onChange={(e) => change(setEnd)(e.target.value)}
          />
        </label>
        <a className="button" href={"/api/export.csv?" + query}>
          ↓ Xuất CSV yêu cầu
        </a>
      </div>
      {error ? (
        <div className="banner danger">
          {error}
          <button onClick={() => void load()}>Thử lại</button>
        </div>
      ) : !history ? (
        <div className="skeleton" />
      ) : !history.items.length ? (
        <div className="empty">
          <h3>Chưa có lịch sử phù hợp</h3>
          <p>Yêu cầu đã lưu sẽ xuất hiện tại đây.</p>
          <button
            onClick={() => {
              setTable("");
              setCategory("");
              setStaff("");
              setState("");
              setStart("");
              setEnd("");
              setOffset(0);
            }}
          >
            Xóa bộ lọc
          </button>
        </div>
      ) : (
        <>
          <div className="history-scroll">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Bàn</th>
                  <th>Loại</th>
                  <th>Trạng thái</th>
                  <th>Nhân viên</th>
                  <th>Trung tâm ghi nhận</th>
                  <th>Hoàn tất</th>
                  <th>Thời gian</th>
                  <th>Chi tiết</th>
                </tr>
              </thead>
              <tbody>
                {history.items.map((r) => (
                  <tr key={r.id}>
                    <td>{r.seq}</td>
                    <td>{r.table_name}</td>
                    <td>{categoryLabels[r.category]}</td>
                    <td>
                      <span className={`badge ${r.state}`}>
                        {labels[r.state]}
                      </span>
                    </td>
                    <td>{r.staff_name ?? "—"}</td>
                    <td>{stamp(r.received_at)}</td>
                    <td>{stamp(r.completed_at)}</td>
                    <td>
                      {r.completed_at === null
                        ? "—"
                        : duration(r.completed_at - r.received_at)}
                    </td>
                    <td>
                      <button onClick={() => onDetail(r.id)}>Xem</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            offset={offset}
            shown={history.items.length}
            total={history.total}
            unit="yêu cầu"
            setOffset={setOffset}
          />
        </>
      )}
    </>
  );
}

function EventHistory({
  data,
  onDetail,
}: {
  data: Snapshot;
  onDetail: (id: string) => void;
}) {
  const [log, setLog] = useState<EventLog | null>(null),
    [error, setError] = useState(""),
    [kind, setKind] = useState(""),
    [table, setTable] = useState(""),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [offset, setOffset] = useState(0);
  const filters = new URLSearchParams();
  if (kind) filters.set("type", kind);
  if (table) filters.set("table_id", table);
  if (start) filters.set("start", epoch(start));
  if (end) filters.set("end", epoch(end));
  const exportQuery = filters.toString();
  filters.set("limit", String(PAGE));
  filters.set("offset", String(offset));
  const query = filters.toString();
  const load = useCallback(async () => {
    setError("");
    try {
      setLog(eventLogSchema.parse(await api("/event-log?" + query)));
    } catch (e) {
      setError(message(e));
    }
  }, [query]);
  // A new filter shows the loading state; new events at the centre refresh in place.
  useEffect(() => setLog(null), [query]);
  useEffect(() => {
    void load();
  }, [load, data.generation]);
  const change = (set: (value: string) => void) => (value: string) => {
    set(value);
    setOffset(0);
  };
  return (
    <>
      <div className="history-filters">
        <label>
          Loại sự kiện
          <select
            value={kind}
            onChange={(e) => change(setKind)(e.target.value)}
          >
            <option value="">Tất cả</option>
            {Object.entries(eventLabels).map(([key, name]) => (
              <option key={key} value={key}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Bàn
          <select
            value={table}
            onChange={(e) => change(setTable)(e.target.value)}
          >
            <option value="">Tất cả</option>
            {data.tables.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Từ thời gian (VN)
          <input
            type="datetime-local"
            value={start}
            onChange={(e) => change(setStart)(e.target.value)}
          />
        </label>
        <label>
          Đến thời gian (VN)
          <input
            type="datetime-local"
            value={end}
            onChange={(e) => change(setEnd)(e.target.value)}
          />
        </label>
        <a className="button" href={"/api/events.csv?" + exportQuery}>
          ↓ Xuất CSV sự kiện
        </a>
      </div>
      {error ? (
        <div className="banner danger">
          {error}
          <button onClick={() => void load()}>Thử lại</button>
        </div>
      ) : !log ? (
        <div className="skeleton" />
      ) : !log.items.length ? (
        <div className="empty">
          <h3>Chưa có sự kiện phù hợp</h3>
          <p>Trung tâm chỉ ghi những gì chính nó quan sát được.</p>
        </div>
      ) : (
        <>
          <div className="history-scroll">
            <table>
              <thead>
                <tr>
                  <th>Thời gian trung tâm</th>
                  <th>Sự kiện</th>
                  <th>Bàn</th>
                  <th>Loại</th>
                  <th>Yêu cầu</th>
                  <th>Nhân viên</th>
                  <th>Nguồn</th>
                  <th>Chi tiết</th>
                </tr>
              </thead>
              <tbody>
                {log.items.map((e) => (
                  <tr key={e.id}>
                    <td>{stamp(e.received_at)}</td>
                    <td>
                      <span className={`badge event-${e.type}`}>
                        {eventLabels[e.type] ?? e.type}
                      </span>
                    </td>
                    <td>{e.table_name ?? "—"}</td>
                    <td>{e.category ? categoryLabels[e.category] : "—"}</td>
                    <td>
                      {e.request_seq === null ? (
                        "—"
                      ) : (
                        <RequestLink event={e} onDetail={onDetail} />
                      )}
                    </td>
                    <td>{e.staff_name ?? "—"}</td>
                    <td>{sourceLabels[e.source] ?? e.source}</td>
                    <td>{reasonText(e.reason) || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            offset={offset}
            shown={log.items.length}
            total={log.total}
            unit="sự kiện"
            setOffset={setOffset}
          />
        </>
      )}
    </>
  );
}

function RequestLink({
  event,
  onDetail,
}: {
  event: EventLog["items"][number];
  onDetail: (id: string) => void;
}) {
  const id = event.request_id;
  return id ? (
    <button onClick={() => onDetail(id)}>#{event.request_seq}</button>
  ) : (
    <>#{event.request_seq}</>
  );
}
