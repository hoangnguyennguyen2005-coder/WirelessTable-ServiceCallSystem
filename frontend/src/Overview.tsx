import {
  categoryLabels,
  clock,
  duration,
  isOverdue,
  labels,
  requestIssues,
  stage,
  stageLabels,
  tableApplied,
  type ServiceRequest,
  type Snapshot,
  type Staff,
  type Table,
} from "./api";

export type Filter =
  | "all"
  | "REGISTERED"
  | "ACKNOWLEDGED"
  | "unassigned"
  | "awaiting"
  | "overdue"
  | "attention"
  | "idle";

const metrics: { filter: Filter; name: string; hint: string }[] = [
  {
    filter: "REGISTERED",
    name: "Chờ xác nhận",
    hint: "Đèn bàn đang đỏ, cần quản lý xác nhận",
  },
  {
    filter: "unassigned",
    name: "Chưa giao việc",
    hint: "Chưa gửi tới thiết bị nhân viên",
  },
  {
    filter: "awaiting",
    name: "Chờ nhân viên nhận",
    hint: "Đã giao, chưa có xác nhận nhận việc",
  },
  {
    filter: "overdue",
    name: "Quá 5 phút",
    hint: "Tính từ lúc trung tâm ghi nhận",
  },
];

export function Overview({
  data,
  now,
  filter,
  setFilter,
  sound,
  toggleSound,
  onSelect,
  onOpen,
}: {
  data: Snapshot;
  now: number;
  filter: Filter;
  setFilter: (filter: Filter) => void;
  sound: boolean;
  toggleSound: () => void;
  onSelect: (tableId: number) => void;
  onOpen: (page: "simulator" | "settings") => void;
}) {
  const { tables, requests: active, limits } = data;
  const tableOf = (r: ServiceRequest) =>
    tables.find((t) => t.id === r.table_id);
  const staffOf = (id: number | null) => data.staff.find((s) => s.id === id);
  const issuesOf = (r: ServiceRequest) =>
    requestIssues(r, tableOf(r), staffOf(r.staff_id), now, limits);
  const matchRequest = (kind: Filter, r: ServiceRequest) => {
    if (kind === "overdue") return isOverdue(r, now, limits);
    if (kind === "unassigned") return stage(r) === "NONE";
    if (kind === "awaiting")
      return stage(r) === "DISPATCHED" || stage(r) === "DELIVERED";
    if (kind === "attention") return issuesOf(r).length > 0;
    return r.state === kind;
  };
  const matches = (r: ServiceRequest | undefined) =>
    filter === "all"
      ? true
      : filter === "idle"
        ? !r
        : !!r && matchRequest(filter, r);
  const counts = metrics.map(
    (m) => active.filter((r) => matchRequest(m.filter, r)).length,
  );
  const attention: { key: string; tableId: number | null; text: string }[] = [];
  for (const r of active)
    for (const issue of issuesOf(r))
      attention.push({
        key: `${r.id}:${issue.key}`,
        tableId: r.table_id,
        text: `${tableOf(r)?.name ?? `Bàn ${r.table_id}`} · ${issue.text}`,
      });
  for (const t of tables)
    if (t.battery_low)
      attention.push({
        key: `battery:${t.id}`,
        tableId: t.id,
        text: `${t.name} · Pin yếu${t.battery_mv === null ? "" : ` (${t.battery_mv} mV)`}`,
      });
  for (const s of data.staff)
    if (s.battery_low)
      attention.push({
        key: `staff-battery:${s.id}`,
        tableId: null,
        text: `Thiết bị của ${s.name} · Pin yếu`,
      });
  const visible = tables.filter((t) =>
    matches(active.find((r) => r.table_id === t.id)),
  );
  return (
    <>
      <div className="section-heading">
        <div>
          <span className="eyebrow">CA PHỤC VỤ HIỆN TẠI</span>
          <h2>Tổng quan tại quán</h2>
          <p>Theo dõi yêu cầu, xác nhận và điều phối phục vụ.</p>
        </div>
        <button className="quiet" aria-pressed={sound} onClick={toggleSound}>
          {sound ? "♪ Âm báo: bật" : "♩ Âm báo: tắt"}
        </button>
      </div>
      <div className="metrics">
        {metrics.map((m, i) => (
          <button
            key={m.filter}
            className={`metric metric-${i}`}
            onClick={() => setFilter(m.filter)}
          >
            <span>{m.name}</span>
            <strong>{counts[i]}</strong>
            <small>{m.hint}</small>
          </button>
        ))}
      </div>
      {attention.length > 0 && (
        <section className="attention" aria-label="Cần chú ý">
          <h3>
            Cần chú ý <span className="count">{attention.length}</span>
          </h3>
          <ul>
            {attention.map((item) => (
              <li key={item.key}>
                {item.tableId === null ? (
                  <span>{item.text}</span>
                ) : (
                  <button onClick={() => onSelect(item.tableId!)}>
                    {item.text}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      <div className="operations">
        <section>
          <div className="grid-heading">
            <h3>
              Sơ đồ bàn{" "}
              <span className="subtle">
                {tables.length} bàn · {active.length} yêu cầu
              </span>
            </h3>
            <select
              aria-label="Lọc bàn"
              value={filter}
              onChange={(e) => setFilter(e.target.value as Filter)}
            >
              <option value="all">Tất cả bàn</option>
              <option value="REGISTERED">Chờ xác nhận</option>
              <option value="ACKNOWLEDGED">Đã xác nhận</option>
              <option value="unassigned">Chưa giao việc</option>
              <option value="awaiting">Chờ nhân viên nhận</option>
              <option value="overdue">Quá 5 phút</option>
              <option value="attention">Cần chú ý</option>
              <option value="idle">Bàn rảnh</option>
            </select>
          </div>
          <div className="legend">
            <span>
              <i className="dot neutral" />
              Bàn rảnh
            </span>
            <span>
              <i className="dot red" />
              Chờ xác nhận · đèn đỏ
            </span>
            <span>
              <i className="dot on" />
              Đã xác nhận · đèn xanh
            </span>
            <span>◷ Quá hạn và giao việc là thông tin riêng</span>
          </div>
          <div className="table-grid">
            {visible.map((t) => {
              const r = active.find((x) => x.table_id === t.id);
              return (
                <TableTile
                  key={t.id}
                  table={t}
                  request={r}
                  now={now}
                  data={data}
                  staff={staffOf(r?.staff_id ?? null)}
                  onClick={() => onSelect(t.id)}
                />
              );
            })}
          </div>
          {!tables.length && (
            <div className="empty">
              <h3>Chưa đăng ký bàn</h3>
              <p>Đăng ký node trước khi kết nối gateway.</p>
              <button onClick={() => onOpen("settings")}>Mở cấu hình</button>
            </div>
          )}
          {tables.length > 0 && !visible.length && (
            <div className="empty">
              <p>Không có bàn phù hợp bộ lọc.</p>
              <button onClick={() => setFilter("all")}>Xem tất cả</button>
            </div>
          )}
          <footer className="grid-footer">
            ◉ Màu trên màn hình biểu thị nghiệp vụ. Đèn thật tại bàn chỉ được
            coi là đã đổi khi nút bàn báo về, xem ở chi tiết bàn.
          </footer>
        </section>
        <aside className="queue">
          <div className="grid-heading">
            <h3>
              Hàng đợi phục vụ
              <span className="subtle">Theo thứ tự trung tâm ghi nhận</span>
            </h3>
            <span className="count">{active.length}</span>
          </div>
          {!active.length ? (
            <div className="empty compact">
              <span>✓</span>
              <h3>Tất cả đã sẵn sàng</h3>
              <p>Yêu cầu mới sẽ xuất hiện tại đây.</p>
              {data.mode === "simulation" && (
                <button onClick={() => onOpen("simulator")}>
                  Mở bàn mô phỏng
                </button>
              )}
            </div>
          ) : (
            active.map((r, index) => {
              const overdue = isOverdue(r, now, limits);
              return (
                <button
                  className="queue-item"
                  key={r.id}
                  onClick={() => onSelect(r.table_id)}
                >
                  <div className="row">
                    <strong>
                      <span className="position">{index + 1}</span>
                      {tableOf(r)?.name ?? `Bàn ${r.table_id}`}
                    </strong>
                    <time className={overdue ? "overdue-text" : ""}>
                      {duration(now - r.received_at)}
                    </time>
                  </div>
                  <div className="row wrap">
                    <span className={`chip ${r.category}`}>
                      {categoryLabels[r.category]}
                    </span>
                    <span className={`badge ${r.state}`}>
                      {labels[r.state]}
                    </span>
                    {overdue && <span className="overdue">Quá hạn</span>}
                  </div>
                  <small>
                    {r.staff_id === null
                      ? stageLabels.NONE
                      : `${staffOf(r.staff_id)?.name ?? "Nhân viên"} · ${stageLabels[stage(r)]}`}
                  </small>
                </button>
              );
            })
          )}
          <div className="queue-footer">
            <span>Đã hoàn tất</span>
            <strong>{data.stats.completed}</strong>
            <small>
              TB từ ghi nhận đến hoàn tất:{" "}
              {data.stats.average_seconds === null
                ? "Chưa có dữ liệu"
                : duration(data.stats.average_seconds)}
            </small>
          </div>
          <StaffDevices data={data} now={now} />
        </aside>
      </div>
    </>
  );
}

function TableTile({
  table,
  request: r,
  now,
  data,
  staff,
  onClick,
}: {
  table: Table;
  request?: ServiceRequest;
  now: number;
  data: Snapshot;
  staff?: Staff;
  onClick: () => void;
}) {
  const issues = r ? requestIssues(r, table, staff, now, data.limits) : [];
  return (
    <button
      className={`table-tile ${r?.state ?? "idle"} ${table.enabled ? "" : "disabled-table"}`}
      onClick={onClick}
      aria-label={`${table.name} — ${r ? `${categoryLabels[r.category]} · ${labels[r.state]}` : "Bàn rảnh"}`}
    >
      <div className="row">
        <strong title={table.name}>{table.name}</strong>
        <span aria-hidden="true">{r ? "◉" : "○"}</span>
      </div>
      {r ? (
        <>
          <div className="row wrap">
            <span className={`chip ${r.category}`}>
              {categoryLabels[r.category]}
            </span>
            <span className="table-state">{labels[r.state]}</span>
          </div>
          <b className="wait">{duration(now - r.received_at)}</b>
          <small title={staff?.name}>
            {r.staff_id === null
              ? stageLabels.NONE
              : `${staff?.name ?? "Nhân viên"} · ${stageLabels[stage(r)]}`}
          </small>
          {isOverdue(r, now, data.limits) && (
            <span className="overdue">◷ Quá 5 phút</span>
          )}
          {issues.map((issue) => (
            <span className="issue" key={issue.key}>
              ⚠ {issue.text}
            </span>
          ))}
          <small className="sync-label">
            {tableApplied(table, r) ? "✓ Bàn đã hiển thị" : "↻ Chờ bàn nhận"}
          </small>
        </>
      ) : (
        <>
          <span className="table-state">
            {table.enabled ? "Bàn rảnh" : "Đã tắt"}
          </span>
          <span className="idle-line">—</span>
          <small>Đang ngủ / chưa có dữ liệu</small>
        </>
      )}
      {table.battery_low ? <span className="issue">▮ Pin yếu</span> : null}
    </button>
  );
}

function StaffDevices({ data, now }: { data: Snapshot; now: number }) {
  const staff = data.staff.filter((s) => s.active);
  if (!staff.length) return null;
  return (
    <div className="staff-devices">
      <h3>Thiết bị nhân viên</h3>
      {staff.map((s) => {
        const tasks = data.requests.filter((r) => r.staff_id === s.id).length;
        const online =
          s.last_seen !== null &&
          now - s.last_seen <= data.limits.staff_contact_seconds;
        return (
          <div className="staff-device-row" key={s.id}>
            <div className="row">
              <strong title={s.name}>{s.name}</strong>
              <span className="subtle">{tasks} việc</span>
            </div>
            <small>
              {s.device_id === null ? (
                "Chưa gán thiết bị"
              ) : (
                <>
                  <i className={online ? "dot on" : "dot"} /> #{s.device_id} ·{" "}
                  {s.last_seen === null
                    ? "Chưa thấy thiết bị"
                    : online
                      ? "Đang liên lạc"
                      : `Mất liên lạc từ ${clock(s.last_seen)}`}
                  {s.battery_low ? " · Pin yếu" : ""}
                  {s.available ? "" : " · Tạm nghỉ"}
                </>
              )}
            </small>
          </div>
        );
      })}
    </div>
  );
}
