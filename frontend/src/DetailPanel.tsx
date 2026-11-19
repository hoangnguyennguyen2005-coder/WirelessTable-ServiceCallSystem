import {
  categoryLabels,
  duration,
  eventLabels,
  isOverdue,
  labels,
  reasonText,
  requestIssues,
  stage,
  stamp,
  tableApplied,
  type Detail,
  type ServiceRequest,
  type Snapshot,
  type Table,
} from "./api";

const commandStatus: Record<string, string> = {
  pending: "Chờ thiết bị liên lạc",
  gateway_received: "Gateway đã nhận",
  applied: "Thiết bị đã áp dụng",
  superseded: "Đã thay bằng lệnh mới",
  failed: "Chưa được xác nhận sau 5 lần",
  expired: "Hết hạn",
};
const commandNames: Record<string, string> = {
  CALL_RECEIPT: "Xác nhận đăng ký · đèn đỏ",
  SET_REQUEST_STATUS: "Trạng thái đèn bàn",
  DONE_RECEIPT: "Xác nhận hoàn tất · tắt đèn",
  DISPATCH: "Giao việc",
  ACCEPT_RECEIPT: "Xác nhận đã nhận việc",
  DISPATCH_CANCEL: "Gỡ việc khỏi thiết bị",
};
const closedLabels: Record<string, string> = {
  REGISTERED: "chưa được quản lý xác nhận",
  ACKNOWLEDGED: "đã được quản lý xác nhận",
  NONE: "chưa giao việc",
  DISPATCHED: "đã giao, chưa tới thiết bị",
  DELIVERED: "đã tới thiết bị, chưa nhận",
  ACCEPTED: "nhân viên đã nhận",
};
const revokeLabels: Record<string, string> = {
  reassigned: "Đã thu hồi do giao lại",
  cancelled: "Quản lý đã thu hồi",
  completed: "Đóng khi yêu cầu hoàn tất",
};

export function DetailPanel({
  data,
  now,
  table,
  detail,
  detailId,
  error,
  pending,
  onAction,
  onRetry,
  onClose,
  onSimulator,
}: {
  data: Snapshot;
  now: number;
  table?: Table;
  detail: Detail | null;
  detailId?: string;
  error: string;
  pending: boolean;
  onAction: (
    r: ServiceRequest,
    kind: string,
    extra?: Record<string, unknown>,
  ) => void;
  onRetry: () => void;
  onClose: () => void;
  onSimulator: () => void;
}) {
  const r = detail?.request;
  const requestTable = r ? data.tables.find((t) => t.id === r.table_id) : table;
  return (
    <aside className="detail-panel" role="dialog" aria-label="Chi tiết bàn">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">CHI TIẾT YÊU CẦU</span>
          <h2>{requestTable?.name ?? table?.name ?? "Lịch sử"}</h2>
        </div>
        <button autoFocus aria-label="Đóng chi tiết" onClick={onClose}>
          ×
        </button>
      </div>
      {error ? (
        <div className="banner danger">
          {error}
          <button onClick={onRetry}>Thử lại</button>
        </div>
      ) : detailId && !r ? (
        <>
          <div className="skeleton" />
          <div className="skeleton" />
        </>
      ) : r && detail ? (
        <RequestDetail
          data={data}
          now={now}
          table={requestTable}
          detail={detail}
          pending={pending}
          onAction={onAction}
        />
      ) : (
        <div className="empty">
          <h3>Bàn đang rảnh</h3>
          <p>
            {table?.enabled
              ? "Nút bàn đang ngủ hoặc chưa có dữ liệu."
              : "Bàn đã tắt sử dụng."}
          </p>
          {table && <Battery table={table} />}
          {data.mode === "simulation" && (
            <button onClick={onSimulator}>Mở nút mô phỏng</button>
          )}
        </div>
      )}
    </aside>
  );
}

function Battery({ table }: { table: Table }) {
  return (
    <small className={table.battery_low ? "overdue-text" : undefined}>
      Pin:{" "}
      {table.battery_mv === null
        ? table.battery_low
          ? "Nút bàn báo pin yếu"
          : "Chưa có dữ liệu"
        : `${table.battery_mv} mV${table.battery_low ? " · Pin yếu, cần thay" : ""}`}
    </small>
  );
}

function RequestDetail({
  data,
  now,
  table,
  detail,
  pending,
  onAction,
}: {
  data: Snapshot;
  now: number;
  table?: Table;
  detail: Detail;
  pending: boolean;
  onAction: (
    r: ServiceRequest,
    kind: string,
    extra?: Record<string, unknown>,
  ) => void;
}) {
  const r = detail.request;
  const live = data.requests.find((x) => x.id === r.id);
  const open = r.state !== "COMPLETED";
  const staff = data.staff.find((s) => s.id === r.staff_id);
  const current = stage(r);
  const applied = tableApplied(table, r);
  const appliedAt = live?.table_command?.applied_at ?? null;
  const issues = requestIssues(live ?? r, table, staff, now, data.limits);
  const [closedState, closedStage] = (r.closed_from ?? "").split("/");
  return (
    <>
      <div className="row wrap start">
        <span className="position">#{r.seq}</span>
        <span className={`chip ${r.category}`}>
          {categoryLabels[r.category]}
        </span>
        <span className={`badge ${r.state}`}>{labels[r.state]}</span>
        {isOverdue(r, now, data.limits) && (
          <span className="overdue">◷ Quá 5 phút</span>
        )}
      </div>
      <h3>
        {open ? "Đã chờ " : "Tổng thời gian "}
        {duration((r.completed_at ?? now) - r.received_at)}
      </h3>
      <p className="subtle">Trung tâm ghi nhận lúc {stamp(r.received_at)}</p>
      {issues.length > 0 && (
        <ul className="issue-list" aria-label="Chưa giải quyết">
          {issues.map((issue) => (
            <li key={issue.key}>⚠ {issue.text}</li>
          ))}
        </ul>
      )}
      {table && (
        <div className="device-sync">
          <strong>
            {applied
              ? `Bàn báo đã hiển thị: ${table.led === "GREEN" ? "đèn xanh" : table.led === "RED" ? "đèn đỏ" : "đèn tắt"}`
              : open
                ? "Đang chờ bàn nhận trạng thái"
                : "Đang chờ bàn xác nhận tắt đèn"}
          </strong>
          {applied && appliedAt !== null && appliedAt >= r.led_changed_at && (
            <small>
              Bàn hiển thị sau {(appliedAt - r.led_changed_at).toFixed(1)} giây
              (đo tại trung tâm)
            </small>
          )}
          <small>Lần cuối bàn liên lạc: {stamp(table.last_seen)}</small>
          <Battery table={table} />
        </div>
      )}
      {r.state === "REGISTERED" && (
        <>
          <button
            className="primary full"
            disabled={pending}
            onClick={() => onAction(r, "ack")}
          >
            {pending ? "Đang lưu…" : "Xác nhận yêu cầu"}
          </button>
          <p className="subtle">
            Đèn bàn chuyển xanh khi nút bàn nhận được xác nhận ở lần liên lạc kế
            tiếp. Giao việc không thay cho bước này.
          </p>
        </>
      )}
      {open && (
        <label>
          {r.staff_id === null
            ? "Giao cho nhân viên"
            : "Giao lại cho nhân viên khác"}
          <select
            aria-label="Giao cho nhân viên"
            disabled={pending}
            value=""
            onChange={(e) => {
              const accepted = r.accepted_at !== null;
              if (
                !accepted ||
                confirm("Nhân viên đã nhận. Xác nhận thu hồi và giao lại?")
              )
                onAction(r, "dispatch", {
                  staff_id: Number(e.target.value),
                  confirm: accepted,
                });
            }}
          >
            <option value="">Chọn nhân viên khả dụng…</option>
            {data.staff
              .filter((s) => s.active && s.available)
              .map((s) => (
                <option
                  key={s.id}
                  value={s.id}
                  disabled={s.device_id === null || s.id === r.staff_id}
                >
                  {s.name}
                  {s.device_id === null
                    ? " (chưa gán thiết bị)"
                    : s.id === r.staff_id
                      ? " (đang giao)"
                      : ""}
                </option>
              ))}
          </select>
        </label>
      )}
      {open && r.staff_id !== null && (
        <div className="instruction">
          <strong>
            {staff?.name ?? "Nhân viên"} · phiên {r.assignment_revision}
          </strong>
          <ol className="steps">
            <li className="done">Đã gửi lệnh lúc {stamp(r.dispatched_at)}</li>
            <li className={r.delivered_at !== null ? "done" : "waiting"}>
              {r.delivered_at !== null
                ? `Thiết bị đã hiển thị lúc ${stamp(r.delivered_at)}`
                : "Chưa tới thiết bị"}
            </li>
            <li className={r.accepted_at !== null ? "done" : "waiting"}>
              {r.accepted_at !== null
                ? `Nhân viên đã nhận lúc ${stamp(r.accepted_at)}`
                : "Chờ nhân viên nhận"}
            </li>
          </ol>
          <div className="row wrap start">
            {current !== "ACCEPTED" && (
              <button
                disabled={pending}
                onClick={() => onAction(r, "retry-dispatch")}
              >
                Gửi lại
              </button>
            )}
            <button
              disabled={pending}
              onClick={() => {
                const accepted = r.accepted_at !== null;
                if (
                  !accepted ||
                  confirm("Nhân viên đã nhận. Xác nhận thu hồi việc này?")
                )
                  onAction(r, "cancel-dispatch", { confirm: accepted });
              }}
            >
              Thu hồi giao việc
            </button>
          </div>
        </div>
      )}
      {open ? (
        <p className="subtle">
          Hoàn tất chỉ bằng cách bấm đúp nút ẩn tại bàn. Web và thiết bị nhân
          viên không có thao tác đóng yêu cầu.
        </p>
      ) : (
        <div className="instruction">
          Hoàn tất tại bàn lúc {stamp(r.completed_at)}
          {r.closed_from && (
            <>
              <br />
              Khi đóng: {closedLabels[closedState] ?? closedState}
              {closedStage
                ? ` · ${closedLabels[closedStage] ?? closedStage}`
                : ""}
              {r.staff_id !== null && staff ? ` (${staff.name})` : ""}
            </>
          )}
        </div>
      )}
      {detail.assignments.length > 0 && (
        <>
          <h3>Lịch sử giao việc</h3>
          {detail.assignments.map((a) => (
            <p className="subtle" key={a.revision}>
              Phiên {a.revision} · {a.staff_name}:{" "}
              {a.accepted_at
                ? "đã nhận việc"
                : a.delivered_at
                  ? "thiết bị đã hiển thị"
                  : "chưa tới thiết bị"}
              {a.revoked_at
                ? ` · ${revokeLabels[a.revoke_reason ?? ""] ?? "Đã thu hồi"}`
                : ""}
            </p>
          ))}
        </>
      )}
      <h3>Lệnh tới thiết bị</h3>
      <div className="command-list">
        {detail.commands.map((c) => (
          <div key={c.command_id}>
            <strong>
              {c.channel === "staff" ? "Nhân viên" : "Bàn"} ·{" "}
              {commandNames[c.type] ?? c.type}
            </strong>
            <small>
              {commandStatus[c.status] ?? c.status} · thử {c.attempts}/5
              {c.error ? ` · ${c.error}` : ""}
            </small>
          </div>
        ))}
        {!detail.commands.length && <div>Chưa có lệnh.</div>}
      </div>
      <h3>Nhật ký sự kiện</h3>
      <ol className="timeline">
        {detail.events
          .slice()
          .reverse()
          .map((e) => (
            <li
              key={e.id}
              className={e.type === "FAILURE" ? "failed" : undefined}
            >
              <strong>{eventLabels[e.type] ?? e.type}</strong>
              <small>
                {stamp(e.received_at)}
                {e.staff_name ? ` · ${e.staff_name}` : ""}
              </small>
              {(e.type === "FAILURE" || e.type === "DUPLICATE") && e.reason && (
                <span className="overdue-text">{reasonText(e.reason)}</span>
              )}
            </li>
          ))}
      </ol>
    </>
  );
}
