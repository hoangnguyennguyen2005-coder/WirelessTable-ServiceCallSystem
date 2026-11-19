import { useState } from "react";
import type { Snapshot } from "./api";

export function SettingsPage({
  data,
  pending,
  run,
}: {
  data: Snapshot;
  pending: boolean;
  run: (path: string, body: unknown) => Promise<void>;
}) {
  const [tableId, setTableId] = useState(1),
    [nodeId, setNodeId] = useState(1),
    [tableName, setTableName] = useState("Bàn 01"),
    [enabled, setEnabled] = useState(true),
    [staffId, setStaffId] = useState(1),
    [name, setName] = useState("Minh Anh"),
    [deviceId, setDeviceId] = useState("101"),
    [active, setActive] = useState(true),
    [available, setAvailable] = useState(true);
  const limits = data.limits;
  return (
    <>
      <div className="section-heading">
        <div>
          <span className="eyebrow">THIẾT LẬP TẠI QUÁN</span>
          <h2>Bàn, nhân viên & thiết bị</h2>
          <p>
            Chỉ truy cập trên máy trung tâm (loopback). Chưa hỗ trợ LAN hoặc
            Internet.
          </p>
        </div>
      </div>
      <div className="settings-grid">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run("/config/tables", {
              id: tableId,
              node_id: nodeId,
              name: tableName,
              enabled,
            });
          }}
        >
          <h3>Đăng ký / sửa bàn</h3>
          <label>
            Bàn hiện có
            <select
              value=""
              onChange={(e) => {
                const t = data.tables.find(
                  (t) => t.id === Number(e.target.value),
                );
                if (t) {
                  setTableId(t.id);
                  setNodeId(t.node_id);
                  setTableName(t.name);
                  setEnabled(Boolean(t.enabled));
                }
              }}
            >
              <option value="">Chọn để chỉnh sửa…</option>
              {data.tables.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            ID bàn
            <input
              type="number"
              min="1"
              max="65535"
              required
              value={tableId}
              onChange={(e) => setTableId(Number(e.target.value))}
            />
          </label>
          <label>
            Node ID (địa chỉ nút bàn)
            <input
              type="number"
              min="1"
              max="65535"
              required
              value={nodeId}
              onChange={(e) => setNodeId(Number(e.target.value))}
            />
          </label>
          <label>
            Tên hiển thị
            <input
              required
              maxLength={80}
              value={tableName}
              onChange={(e) => setTableName(e.target.value)}
            />
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            Bật sử dụng
          </label>
          <button className="primary" disabled={pending}>
            Lưu bàn
          </button>
        </form>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run("/config/staff", {
              id: staffId,
              name,
              active,
              available,
              device_id: deviceId === "" ? null : Number(deviceId),
            });
          }}
        >
          <h3>Nhân viên và thiết bị</h3>
          <label>
            Nhân viên hiện có
            <select
              value=""
              onChange={(e) => {
                const s = data.staff.find(
                  (s) => s.id === Number(e.target.value),
                );
                if (s) {
                  setStaffId(s.id);
                  setName(s.name);
                  setDeviceId(s.device_id === null ? "" : String(s.device_id));
                  setActive(Boolean(s.active));
                  setAvailable(Boolean(s.available));
                }
              }}
            >
              <option value="">Chọn để chỉnh sửa…</option>
              {data.staff.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            ID nhân viên
            <input
              type="number"
              min="1"
              required
              value={staffId}
              onChange={(e) => setStaffId(Number(e.target.value))}
            />
          </label>
          <label>
            Tên
            <input
              required
              maxLength={80}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label>
            ID thiết bị nhân viên
            <input
              type="number"
              min="1"
              max="65535"
              value={deviceId}
              onChange={(e) => setDeviceId(e.target.value)}
            />
            <small>
              Địa chỉ thiết bị cầm tay, không trùng node ID của bàn. Để trống
              nếu chưa có thiết bị (khi đó không giao việc được).
            </small>
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={active}
              onChange={(e) => setActive(e.target.checked)}
            />
            Đang hoạt động
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={available}
              onChange={(e) => setAvailable(e.target.checked)}
            />
            Khả dụng để nhận việc
          </label>
          <button className="primary" disabled={pending}>
            Lưu nhân viên
          </button>
        </form>
        <section className="system-info">
          <h3>Thông số đang dùng</h3>
          <dl>
            <dt>Mã quán (venue)</dt>
            <dd>{data.venue_id}</dd>
            <dt>Giữ nút để gọi</dt>
            <dd>{limits.hold_seconds} giây</dd>
            <dt>Kết quả đăng ký tại bàn</dt>
            <dd>trong {limits.registration_seconds} giây</dd>
            <dt>Nhắc quản lý</dt>
            <dd>từ {limits.reminder_seconds} giây</dd>
            <dt>Ngưỡng chưa giải quyết</dt>
            <dd>{limits.unresolved_seconds} giây</dd>
            <dt>Chu kỳ liên lạc bàn / nhân viên</dt>
            <dd>
              {limits.poll_seconds} / {limits.staff_poll_seconds} giây
            </dd>
            <dt>Cửa sổ bấm đúp</dt>
            <dd>{data.double_ms} ms</dd>
            <dt>Lưu nhật ký sự kiện</dt>
            <dd>{limits.retention_days} ngày</dd>
          </dl>
          <small>
            Các mốc thời gian là giá trị đề xuất trong logbook, còn chờ thử với
            người dùng và firmware. Đổi bằng biến môi trường PBL_*.
          </small>
        </section>
      </div>
    </>
  );
}
