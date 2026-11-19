import { useEffect, useRef } from "react";
import {
  api,
  categoryLabels,
  type Category,
  type SimNode,
  type Snapshot,
} from "./api";

type Send = (body: unknown) => Promise<void>;

/** Indication wording follows the logbook table (Step 6 §6.3); patterns are proposed. */
function patternText(node: SimNode | undefined, seconds: number) {
  switch (node?.pattern) {
    case "hold":
      return `Đang giữ ${seconds.toFixed(1)} / 5 giây · đỏ nhấp nháy`;
    case "pending":
      return "Đã gửi · chờ trung tâm xác nhận đăng ký";
    case "red":
      return "Trung tâm đã ghi nhận · đèn đỏ sáng";
    case "green":
      return "Quản lý đã xác nhận · đèn xanh sáng";
    case "completing":
      return "Đã báo hoàn tất · chờ trung tâm xác nhận";
    case "reconciling":
      return "Nút vừa khởi động · đang đối soát với trung tâm";
    case "unconfirmed":
      return node.phase === "registering"
        ? "Chưa xác nhận được đăng ký · đỏ chớp đôi"
        : node.phase === "reconciling"
          ? "Chưa đối soát được với trung tâm · đỏ chớp đôi"
          : "Mất liên lạc trung tâm · đỏ chớp đôi";
    default:
      return "Đang ngủ · đèn tắt";
  }
}

export function SimulatorPage({
  data,
  now,
  pending,
  tableId,
  onTable,
  sim,
}: {
  data: Snapshot;
  now: number;
  pending: boolean;
  tableId: number | null;
  onTable: (id: number) => void;
  sim: Send;
}) {
  const tables = data.tables.filter((t) => t.enabled);
  const table = tables.find((t) => t.id === tableId) ?? tables[0];
  const simulator = data.simulator;
  if (!simulator) return null;
  return (
    <>
      <div className="section-heading">
        <div>
          <span className="eyebrow">PHÒNG DEMO · DỮ LIỆU MÔ PHỎNG RIÊNG</span>
          <h2>Bàn mô phỏng</h2>
          <p>
            Nút và đèn mô phỏng gửi sự kiện qua cùng luồng với gateway thật và
            lưu SQLite thật.
          </p>
        </div>
        <button
          disabled={pending}
          onClick={() => void sim({ action: "burst" })}
        >
          Gọi đồng thời 4 bàn
        </button>
      </div>
      <div className="sim-layout">
        <section className="sim-console">
          <label>
            Chọn bàn
            <select
              value={table?.id ?? ""}
              onChange={(e) => onTable(Number(e.target.value))}
            >
              {tables.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
          {table ? (
            <TableUnit
              data={data}
              nodeId={table.node_id}
              now={now}
              disabled={pending}
              send={sim}
            />
          ) : (
            <p>Chưa có bàn nào đang bật.</p>
          )}
        </section>
        <section className="faults">
          <h3>Thử tình huống lỗi</h3>
          <p>Các điều khiển này chỉ tồn tại trong chế độ mô phỏng.</p>
          <button
            disabled={pending}
            onClick={() =>
              void sim({
                action: "connection",
                enabled: !data.gateway.connected,
              })
            }
          >
            {data.gateway.connected
              ? "Ngắt gateway mô phỏng"
              : "Kết nối lại gateway"}
          </button>
          <label>
            Lỗi ở gói tiếp theo
            <select
              value={simulator.fault}
              onChange={(e) =>
                void sim({
                  action: "fault",
                  fault: e.target.value,
                  ...(table ? { node_id: table.node_id } : {}),
                })
              }
            >
              <option value="none">Không gây lỗi</option>
              <option value="drop_event">Mất gói từ bàn một lần</option>
              <option value="drop_receipt">
                Mất phản hồi trung tâm một lần
              </option>
              <option value="duplicate">Nhân đôi gói từ bàn</option>
            </select>
            <small>
              {simulator.fault === "none"
                ? "Áp cho gói tiếp theo của bàn đang chọn."
                : `Đang chờ gói tiếp theo của ${
                    data.tables.find((t) => t.node_id === simulator.fault_node)
                      ?.name ?? "bất kỳ bàn nào"
                  }.`}
            </small>
          </label>
          <label>
            Trễ gói đăng ký (giây)
            <input
              type="number"
              min="0"
              max="30"
              value={simulator.delay}
              onChange={(e) =>
                void sim({ action: "delay", seconds: Number(e.target.value) })
              }
            />
          </label>
          <button
            disabled={pending}
            onClick={() => void sim({ action: "advance", seconds: 300 })}
          >
            Tua +300 giây · chỉ đồng hồ demo
          </button>
          <h3>Thiết bị nhân viên mô phỏng</h3>
          {simulator.staff_devices.map((device) => {
            const name =
              data.staff.find((s) => s.id === device.staff_id)?.name ??
              `Nhân viên ${device.staff_id}`;
            return (
              <button
                key={device.staff_id}
                disabled={pending}
                onClick={() =>
                  void sim({
                    action: "staff_power",
                    staff_id: device.staff_id,
                    enabled: !device.powered,
                  })
                }
              >
                {device.powered
                  ? `Tắt nguồn thiết bị ${name}`
                  : `Bật nguồn thiết bị ${name}`}
              </button>
            );
          })}
          <small>
            Thời gian chờ không reset khi xác nhận hoặc giao việc. Chu kỳ liên
            lạc khi có yêu cầu {simulator.poll_seconds} giây; cửa sổ bấm đúp{" "}
            {simulator.double_ms} ms. Đây là giá trị đề xuất, chưa xác nhận với
            firmware.
          </small>
          <button
            className="danger-button"
            disabled={pending}
            onClick={() => {
              if (
                confirm("Xóa toàn bộ lịch sử và yêu cầu trong database DEMO?")
              )
                void sim({ action: "reset", confirm: "RESET DEMO" });
            }}
          >
            Reset dữ liệu demo…
          </button>
        </section>
      </div>
    </>
  );
}

function TableUnit({
  data,
  nodeId,
  now,
  disabled,
  send,
}: {
  data: Snapshot;
  nodeId: number;
  now: number;
  disabled: boolean;
  send: Send;
}) {
  const node = data.simulator?.nodes.find((n) => n.node_id === nodeId);
  const pattern = node?.pattern ?? "off";
  const seconds =
    pattern === "hold" && node && node.hold_at !== null
      ? Math.min(5, Math.max(0, now - node.hold_at))
      : 0;
  const idle = node === undefined || node.phase === "sleep";
  const text = patternText(node, seconds);
  return (
    <>
      <div
        className={`unit-leds pattern-${pattern}`}
        role="img"
        aria-label={`Đèn bàn mô phỏng: ${text}`}
      >
        <i className="led red" />
        <i className="led green" />
      </div>
      <h3>{text}</h3>
      {node?.category && pattern !== "off" && (
        <span className={`chip ${node.category}`}>
          {categoryLabels[node.category]}
        </span>
      )}
      <progress max="5" value={seconds} aria-label="Thời gian giữ nút" />
      <div className="guest-controls">
        {(["SERVICE", "BILL"] as const).map((category) => (
          <HoldButton
            key={category}
            category={category}
            nodeId={nodeId}
            disabled={
              disabled ||
              !(idle || (pattern === "hold" && node?.category === category))
            }
            send={send}
          />
        ))}
      </div>
      <p>
        Thả trước 5 giây để hủy. Đỏ sáng liên tục chỉ sau khi trung tâm xác nhận
        đã ghi nhận; xanh chỉ sau khi quản lý xác nhận.
      </p>
      <button
        className="hidden-button"
        disabled={disabled}
        onClick={() => void send({ action: "hidden", node_id: nodeId })}
      >
        Nút ẩn hoàn tất · bấm hai lần
      </button>
      <small>
        {node?.press_armed
          ? `Đã bấm lần 1 · bấm lần 2 trong ${data.simulator?.double_ms} ms.`
          : `Hai lần bấm riêng trong ${data.simulator?.double_ms} ms, chỉ có tác dụng khi bàn đang có yêu cầu đã ghi nhận. Thiết bị nhân viên không có thao tác này.`}
      </small>
      <div className="row wrap node-tools">
        <button
          disabled={disabled}
          onClick={() => void send({ action: "restart", node_id: nodeId })}
        >
          Khởi động lại nút (thay pin)
        </button>
        <button
          disabled={disabled}
          aria-pressed={node?.battery_low ?? false}
          onClick={() =>
            void send({
              action: "battery",
              node_id: nodeId,
              enabled: !(node?.battery_low ?? false),
            })
          }
        >
          {node?.battery_low ? "Bỏ giả lập pin yếu" : "Giả lập pin yếu"}
        </button>
      </div>
      {node?.error && (
        <p className="overdue-text">Trung tâm từ chối: {node.error}</p>
      )}
    </>
  );
}

function HoldButton({
  category,
  nodeId,
  disabled,
  send,
}: {
  category: Category;
  nodeId: number;
  disabled: boolean;
  send: Send;
}) {
  const down = useRef(false);
  const press = () => {
    down.current = true;
    void send({ action: "press", node_id: nodeId, category });
  };
  const release = () => {
    if (down.current) {
      down.current = false;
      void send({ action: "release", node_id: nodeId, category });
    }
  };
  useEffect(
    () => () => {
      if (down.current) {
        down.current = false;
        void api("/sim/action", {
          action: "release",
          node_id: nodeId,
          category,
        });
      }
    },
    [nodeId, category],
  );
  return (
    <button
      className={`call-button ${category}`}
      disabled={disabled}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        e.currentTarget.setPointerCapture(e.pointerId);
        press();
      }}
      onPointerUp={release}
      onPointerCancel={release}
      onLostPointerCapture={release}
      onKeyDown={(e) => {
        if ((e.key === " " || e.key === "Enter") && !e.repeat) {
          e.preventDefault();
          press();
        }
      }}
      onKeyUp={(e) => {
        if (e.key === " " || e.key === "Enter") {
          e.preventDefault();
          release();
        }
      }}
      onBlur={release}
    >
      {category === "SERVICE" ? "PHỤC VỤ" : "THANH TOÁN"}
      <span>Giữ 5 giây</span>
    </button>
  );
}
