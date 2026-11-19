import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  categoryLabels,
  deviceSchema,
  duration,
  message,
  type Device,
  type Snapshot,
} from "./api";

/**
 * Screen of a virtual staff device. In simulation it is the simulated device; in the hardware
 * profile it only exists as a token-protected bench stub. The product uses a dedicated
 * portable unit through the gateway, never a personal phone (logbook C-04, C-06).
 */
export function StaffDevicePage({
  data,
  now,
}: {
  data: Snapshot;
  now: number;
}) {
  const simulation = data.mode === "simulation";
  const withDevice = data.staff.filter((s) => s.active && s.device_id !== null);
  const [staffId, setStaffId] = useState(withDevice[0]?.id ?? 1),
    [token, setToken] = useState(""),
    [device, setDevice] = useState<Device | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false),
    [busy, setBusy] = useState(false);
  const sequence = useRef(0);
  const available = simulation || data.staff_stub;
  const load = useCallback(async () => {
    if (!available) return;
    const current = ++sequence.current;
    setLoading(true);
    try {
      const value = deviceSchema.parse(
        await api(
          `/staff-device/${staffId}`,
          undefined,
          token ? { "x-staff-token": token } : {},
        ),
      );
      if (current === sequence.current) {
        setDevice(value);
        setError("");
      }
    } catch (e) {
      if (current === sequence.current) {
        setDevice(null);
        setError(message(e));
      }
    } finally {
      if (current === sequence.current) setLoading(false);
    }
  }, [available, staffId, token]);
  useEffect(() => {
    void load();
  }, [load, data.now]);
  const accept = async (requestId: string) => {
    if (busy) return;
    setBusy(true);
    try {
      setDevice(
        deviceSchema.parse(
          await api(
            `/staff-device/${staffId}/accept`,
            { request_id: requestId },
            token ? { "x-staff-token": token } : {},
          ),
        ),
      );
      setError("");
    } catch (e) {
      setError(message(e));
      void load();
    } finally {
      setBusy(false);
    }
  };
  const name =
    data.staff.find((s) => s.id === staffId)?.name ?? `Nhân viên ${staffId}`;
  return (
    <main className="staff-main">
      <div className="section-heading">
        <div>
          <span className="eyebrow">
            THIẾT BỊ NHÂN VIÊN · {simulation ? "MÔ PHỎNG" : "STUB CHẨN ĐOÁN"}
          </span>
          <h2>Công việc của bạn</h2>
          <p>
            Màn hình mô phỏng chức năng thiết bị nhân viên chuyên dụng: hiển thị
            bàn và loại yêu cầu, rung im lặng, một nút nhận việc.
          </p>
        </div>
        <a href="/">← Quản lý</a>
      </div>
      {!available ? (
        <div className="empty">
          <h3>Chế độ phần cứng dùng thiết bị chuyên dụng</h3>
          <p>
            Nhân viên nhận việc trên thiết bị Pro Mini + nRF24 qua gateway.
            Trang này chỉ hoạt động khi bật stub chẩn đoán bằng PBL_STAFF_TOKEN.
          </p>
        </div>
      ) : (
        <>
          <div className="staff-identity">
            {simulation ? (
              <label>
                Chọn thiết bị mô phỏng
                <select
                  value={staffId}
                  onChange={(e) => setStaffId(Number(e.target.value))}
                >
                  {withDevice.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} · thiết bị #{s.device_id}
                    </option>
                  ))}
                </select>
                <small>Bộ chọn demo, không phải cơ chế phân quyền.</small>
              </label>
            ) : (
              <>
                <label>
                  Mã nhân viên của stub
                  <input
                    type="number"
                    min="1"
                    value={staffId}
                    onChange={(e) => setStaffId(Number(e.target.value))}
                  />
                </label>
                <label>
                  Token stub (cấu hình tại trung tâm)
                  <input
                    type="password"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    autoComplete="off"
                  />
                </label>
              </>
            )}
          </div>
          {error && (
            <div className="banner danger" role="alert">
              {error}
              <button onClick={() => void load()}>Kiểm tra cập nhật</button>
            </div>
          )}
          {!device ? (
            loading ? (
              <div className="skeleton" aria-label="Đang tải thiết bị" />
            ) : null
          ) : (
            <section
              className={device.vibrating ? "device vibrating" : "device"}
              aria-label="Màn hình thiết bị nhân viên"
            >
              <header className="row">
                <strong>{name}</strong>
                <span className="subtle">
                  #{device.device_id} ·{" "}
                  {!device.powered
                    ? "Đã tắt nguồn"
                    : device.link_lost
                      ? "Mất liên lạc trung tâm"
                      : "Đang liên lạc"}
                </span>
              </header>
              {device.vibrating && (
                <div className="vibration" role="status">
                  ≋ Thiết bị đang rung · có việc mới
                </div>
              )}
              {!device.tasks.length ? (
                <div className="empty">
                  <span>✓</span>
                  <h3>Chưa có việc được giao</h3>
                  <p>Việc mới hiện khi quản lý giao cho thiết bị này.</p>
                  <button onClick={() => void load()}>Kiểm tra cập nhật</button>
                </div>
              ) : (
                device.tasks.map((task) => (
                  <article className="staff-job" key={task.request_id}>
                    <div className="row">
                      <h2>{task.table_name}</h2>
                      <span className={`chip large ${task.category}`}>
                        {categoryLabels[task.category]}
                      </span>
                    </div>
                    <p>
                      Yêu cầu #{task.request_seq} · phiên giao {task.revision} ·
                      hiện trên máy {duration(now - task.shown_at)}
                    </p>
                    {task.state === "SHOWN" ? (
                      <button
                        className="primary full"
                        disabled={busy}
                        onClick={() => void accept(task.request_id)}
                      >
                        Nhận việc
                      </button>
                    ) : task.state === "ACCEPTING" ? (
                      <div className="instruction">
                        Đã bấm nhận · đang chờ trung tâm xác nhận.
                      </div>
                    ) : (
                      <div className="instruction">
                        Đến bàn phục vụ và bấm đúp nút ẩn để hoàn tất.
                      </div>
                    )}
                  </article>
                ))
              )}
            </section>
          )}
          <p className="subtle">
            Thiết bị không có thao tác đóng yêu cầu. Nhận việc không tắt đèn và
            không thay cho bấm đúp tại bàn.
          </p>
        </>
      )}
    </main>
  );
}
