import { useCallback, useEffect, useRef, useState } from "react";
import { z } from "zod";
import {
  api,
  detailSchema,
  duration,
  historySchema,
  labels,
  requestSchema,
  stamp,
  useLive,
  type Detail,
  type History,
  type ServiceRequest,
  type Snapshot,
  type Table,
} from "./api";

type Page = "overview" | "simulator" | "history" | "settings";
const commandStatus: Record<string, string> = {
  pending: "Chờ gửi",
  gateway_received: "Gateway đã nhận",
  applied: "Bàn đã áp dụng",
  superseded: "Đã thay bằng lệnh mới",
  failed: "Lỗi gửi",
  expired: "Hết hạn",
};
const resultLabels: Record<string, string> = {
  accepted: "Đã xử lý",
  duplicate: "Gói lặp",
  rejected: "Từ chối",
};
const eventLabels: Record<string, string> = {
  CALL: "Bàn gửi yêu cầu",
  ACK: "Quản lý xác nhận",
  ASSIGN: "Giao việc",
  ACCEPT: "Nhân viên nhận việc",
  DONE: "Hoàn tất tại bàn",
  REMINDER: "Nhắc quá 5 phút",
  STATUS_POLL: "Bàn kiểm tra trạng thái",
  STATUS_APPLIED: "Bàn xác nhận trạng thái đèn",
  COMMAND_ACK: "Gateway nhận lệnh",
};

export default function App() {
  const { data, error, connected, refresh } = useLive();
  const [page, setPage] = useState<Page>("overview"),
    [selected, setSelected] = useState<number | null>(null),
    [detail, setDetail] = useState<Detail | null>(null),
    [detailError, setDetailError] = useState("");
  const [pending, setPending] = useState(false),
    [notice, setNotice] = useState(""),
    [filter, setFilter] = useState("all"),
    [staffId, setStaffId] = useState(1),
    [token, setToken] = useState(""),
    [inbox, setInbox] = useState<ServiceRequest[]>([]);
  const [inboxLoading, setInboxLoading] = useState(false);
  const lastIdentity = useRef("");
  const [now, setNow] = useState(Date.now() / 1000),
    [sound, setSound] = useState(false);
  const simQueue = useRef<Promise<void>>(Promise.resolve());
  const audio = useRef<AudioContext | null>(null),
    seen = useRef<Set<string>>(new Set()),
    initialized = useRef(false);
  const staffPage = location.pathname === "/staff";
  const selectedRequest = data?.requests.find((r) => r.table_id === selected);
  const selectedRequestId = selectedRequest?.id,
    selectedVersion = selectedRequest?.version;
  const detailSequence = useRef(0);
  const [historyId, setHistoryId] = useState<string | null>(null);
  const detailId = historyId ?? selectedRequestId;
  const loadDetail = useCallback(async () => {
    const sequence = ++detailSequence.current;
    if (!detailId) {
      setDetail(null);
      return;
    }
    try {
      const value = detailSchema.parse(await api(`/requests/${detailId}`));
      if (sequence === detailSequence.current) {
        setDetail(value);
        setDetailError("");
      }
    } catch (e) {
      if (sequence === detailSequence.current) setDetailError(message(e));
    }
  }, [detailId]);
  useEffect(() => {
    void loadDetail();
    return () => {
      detailSequence.current++;
    };
  }, [loadDetail, selectedVersion, data?.now]);
  useEffect(() => {
    const timer = setInterval(
      () =>
        setNow(
          (data?.now ?? Date.now() / 1000) + (Date.now() / 1000 - started),
        ),
      1000,
    );
    const started = Date.now() / 1000;
    setNow(data?.now ?? started);
    return () => clearInterval(timer);
  }, [data?.now]);
  const inboxKey = data
    ? JSON.stringify(data.requests.map((r) => [r.id, r.version]))
    : "";
  useEffect(() => {
    let cancelled = false;
    if (staffPage && data) {
      const identity = `${staffId}:${token}`;
      if (lastIdentity.current !== identity) {
        setInbox([]);
        lastIdentity.current = identity;
      }
      setInboxLoading(true);
      api(
        `/staff/${staffId}/inbox`,
        undefined,
        token ? { "x-staff-token": token } : {},
      )
        .then((value) => {
          if (!cancelled) {
            setInbox(z.array(requestSchema).parse(value));
            setNotice("");
          }
        })
        .catch((e) => {
          if (!cancelled) {
            setInbox([]);
            setNotice(message(e));
          }
        })
        .finally(() => {
          if (!cancelled) setInboxLoading(false);
        });
    }
    return () => {
      cancelled = true;
    };
  }, [staffPage, staffId, token, inboxKey, data?.mode, data?.now]);
  useEffect(() => {
    if (!data) return;
    const keys = data.requests.flatMap((r) => [
      r.id,
      ...(r.reminded_at ? [r.id + ":overdue"] : []),
    ]);
    if (
      initialized.current &&
      sound &&
      keys.some((k) => !seen.current.has(k)) &&
      audio.current
    ) {
      const oscillator = audio.current.createOscillator(),
        gain = audio.current.createGain();
      oscillator.frequency.value = 660;
      gain.gain.value = 0.08;
      oscillator.connect(gain);
      gain.connect(audio.current.destination);
      oscillator.start();
      oscillator.stop(audio.current.currentTime + 0.16);
    }
    keys.forEach((k) => seen.current.add(k));
    initialized.current = true;
  }, [data, sound]);
  useEffect(
    () => () => {
      void audio.current?.close();
    },
    [],
  );
  const run = async (
    path: string,
    body: unknown,
    headers: Record<string, string> = {},
  ) => {
    if (pending) return;
    setPending(true);
    setNotice("");
    try {
      await api(path, body, headers);
      await refresh();
    } catch (e) {
      setNotice(message(e));
      await refresh();
    } finally {
      setPending(false);
    }
  };
  const sim = (body: unknown) => {
    const task = simQueue.current.then(async () => {
      await api("/sim/action", body);
      await refresh();
    });
    simQueue.current = task.catch((e) => {
      setNotice(message(e));
    });
    return simQueue.current;
  };
  const action = (
    r: ServiceRequest,
    kind: string,
    extra: Record<string, unknown> = {},
  ) =>
    run(
      `/requests/${r.id}/${kind}`,
      {
        expected_version: r.version,
        idempotency_key: crypto.randomUUID(),
        ...extra,
      },
      staffPage && token ? { "x-staff-token": token } : {},
    );
  const close = () => {
    setSelected(null);
    setHistoryId(null);
    setDetail(null);
  };
  if (!data)
    return (
      <main className="initial">
        <div className="brand-mark">P4</div>
        <h1>PBL4 — Gọi phục vụ</h1>
        {error ? (
          <>
            <p role="alert">{error}</p>
            <button onClick={() => void refresh()}>Thử kết nối lại</button>
          </>
        ) : (
          <>
            <p>Đang kết nối trung tâm…</p>
            <div className="skeleton" />
            <div className="skeleton" />
          </>
        )}
      </main>
    );
  const tables = data.tables,
    active = data.requests;
  const tableName = (id: number) =>
    tables.find((t) => t.id === id)?.name ?? `Bàn ${id}`;
  const staffName = (id: number | null) =>
    data.staff.find((s) => s.id === id)?.name ?? "Chưa giao";
  const counts = [
    active.filter((r) => r.state === "WAITING_ACK").length,
    active.filter((r) => r.state === "ACKNOWLEDGED").length,
    active.filter((r) => r.state === "ASSIGNED" || r.state === "ACCEPTED")
      .length,
    active.filter((r) => now - r.received_at > 300).length,
  ];
  const selectedTable = tables.find((t) => t.id === selected);
  const selectTable = (id: number) => {
    setHistoryId(null);
    setSelected(id);
    setDetail(null);
  };
  const toggleSound = () => {
    if (!audio.current) audio.current = new AudioContext();
    void audio.current.resume();
    setSound(!sound);
  };
  return (
    <div className={staffPage ? "app staff-app" : "app"}>
      {!staffPage && (
        <nav className="sidebar" aria-label="Điều hướng chính">
          <a className="brand" href="/">
            <span className="brand-mark">P4</span>
            <span>
              PBL4<small>TRUNG TÂM ĐIỀU PHỐI</small>
            </span>
          </a>
          <div className="nav-label">VẬN HÀNH</div>
          {(
            [
              ["overview", "▦", "Tổng quan"],
              ["simulator", "◎", "Bàn mô phỏng"],
              ["history", "◷", "Lịch sử"],
              ["settings", "⚙", "Cấu hình"],
            ] as const
          )
            .filter(
              ([key]) => key !== "simulator" || data.mode === "simulation",
            )
            .map(([key, icon, label]) => (
              <button
                key={key}
                className={page === key ? "nav-item current" : "nav-item"}
                onClick={() => {
                  setPage(key);
                  close();
                }}
              >
                <span aria-hidden="true">{icon}</span>
                {label}
              </button>
            ))}
          <div className="nav-bottom">
            <a href="/staff" className="staff-link">
              ↗ Giao diện nhân viên
            </a>
            <p>Concept C · Hoạt động tại quán</p>
            <small>Pro Mini → nRF24 → Gateway USB</small>
          </div>
        </nav>
      )}
      <div className="workspace">
        <header className="topbar">
          <div>
            <span className="eyebrow">WIRELESS TABLE CALL SERVICE</span>
            <h1>PBL4 — Gọi phục vụ</h1>
          </div>
          <div className="top-status">
            <span className={`mode ${data.mode}`}>
              {data.mode === "simulation" ? "MÔ PHỎNG" : "PHẦN CỨNG"}
            </span>
            <span className="connection">
              <i className={connected ? "dot on" : "dot"} />
              {connected ? "Trung tâm trực tuyến" : "Đang kết nối lại"}
            </span>
            <time>
              {new Date(now * 1000).toLocaleTimeString("vi-VN", {
                timeZone: "Asia/Ho_Chi_Minh",
                hour12: false,
              })}
            </time>
          </div>
        </header>
        {(!connected || error) && (
          <div className="banner warning" role="status">
            Kết nối trung tâm bị gián đoạn. Đang kết nối lại và tải snapshot.{" "}
            {error}
            <button onClick={() => void refresh()}>Thử lại</button>
          </div>
        )}
        {!data.gateway.connected && (
          <div className="banner warning">
            Gateway đang ngắt · yêu cầu đã lưu vẫn được giữ.{" "}
            {data.gateway.error}
          </div>
        )}
        {notice && (
          <div className="banner danger" role="alert">
            {notice}
            <button onClick={() => setNotice("")}>Đóng</button>
          </div>
        )}
        {staffPage ? (
          <main className="staff-main">
            <div className="section-heading">
              <div>
                <span className="eyebrow">
                  THIẾT BỊ NHÂN VIÊN · WEB PROTOTYPE
                </span>
                <h2>Công việc của bạn</h2>
                <p>Giao diện web mô phỏng chức năng thiết bị nhân viên.</p>
              </div>
              <a href="/">← Quản lý</a>
            </div>
            <div className="staff-identity">
              {data.mode === "simulation" ? (
                <label>
                  Chọn nhân viên demo
                  <select
                    value={staffId}
                    onChange={(e) => setStaffId(Number(e.target.value))}
                  >
                    {data.staff.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                  <small>Bộ chọn demo, không phải cơ chế phân quyền.</small>
                </label>
              ) : (
                <>
                  <label>
                    Mã nhân viên thiết bị
                    <input
                      type="number"
                      min="1"
                      value={staffId}
                      onChange={(e) => setStaffId(Number(e.target.value))}
                    />
                  </label>
                  <label>
                    Token thiết bị (cấu hình tại trung tâm)
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
            <h3>
              {staffName(staffId)}{" "}
              <span className="subtle">· {inbox.length} công việc</span>
            </h3>
            {inboxLoading && !inbox.length ? (
              <div className="skeleton" aria-label="Đang tải công việc" />
            ) : !inbox.length ? (
              <div className="empty">
                <span>✓</span>
                <h3>Chưa có việc được giao</h3>
                <p>Công việc mới sẽ xuất hiện khi quản lý giao cho bạn.</p>
                <button onClick={() => void refresh()}>
                  Kiểm tra cập nhật
                </button>
              </div>
            ) : (
              inbox.map((r) => (
                <article className="staff-job" key={r.id}>
                  <div className="row">
                    <h2>{tableName(r.table_id)}</h2>
                    <span className={`badge ${r.state}`}>
                      {labels[r.state]}
                    </span>
                  </div>
                  <p>
                    Đã chờ {duration(now - r.received_at)} · Phiên giao{" "}
                    {r.assignment_revision}
                  </p>
                  {r.state === "ASSIGNED" ? (
                    <button
                      className="primary full"
                      disabled={pending}
                      onClick={() =>
                        void action(r, "accept", {
                          staff_id: staffId,
                          revision: r.assignment_revision,
                        })
                      }
                    >
                      Nhận việc
                    </button>
                  ) : (
                    <div className="instruction">
                      Đến bàn phục vụ và bấm đúp nút ẩn để hoàn tất.
                    </div>
                  )}
                </article>
              ))
            )}
          </main>
        ) : (
          <main>
            {page === "overview" && (
              <>
                <div className="section-heading">
                  <div>
                    <span className="eyebrow">CA PHỤC VỤ HIỆN TẠI</span>
                    <h2>Tổng quan tại quán</h2>
                    <p>Theo dõi yêu cầu, xác nhận và điều phối phục vụ.</p>
                  </div>
                  <button
                    className="quiet"
                    aria-pressed={sound}
                    onClick={toggleSound}
                  >
                    {sound ? "♪ Âm báo: bật" : "♩ Âm báo: tắt"}
                  </button>
                </div>
                <div className="metrics">
                  {[
                    "Chờ xác nhận",
                    "Đã xác nhận · chưa giao",
                    "Đang giao / phục vụ",
                    "Quá 5 phút",
                  ].map((name, i) => (
                    <button
                      key={name}
                      className={`metric metric-${i}`}
                      onClick={() =>
                        setFilter(
                          ["WAITING_ACK", "ACKNOWLEDGED", "working", "overdue"][
                            i
                          ],
                        )
                      }
                    >
                      <span>{name}</span>
                      <strong>{counts[i]}</strong>
                      <small>
                        {
                          [
                            "Cần quản lý xác nhận",
                            "Sẵn sàng giao cho nhân viên",
                            "Nhân viên đã giao hoặc nhận",
                            "Tính từ lúc trung tâm nhận",
                          ][i]
                        }
                      </small>
                    </button>
                  ))}
                </div>
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
                        onChange={(e) => setFilter(e.target.value)}
                      >
                        <option value="all">Tất cả bàn</option>
                        <option value="WAITING_ACK">Chờ xác nhận</option>
                        <option value="ACKNOWLEDGED">Đã xác nhận</option>
                        <option value="working">Đang phục vụ</option>
                        <option value="overdue">Quá hạn</option>
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
                        Chờ xác nhận
                      </span>
                      <span>
                        <i className="dot on" />
                        Đã xác nhận
                      </span>
                      <span>◷ Quá hạn là cờ riêng</span>
                    </div>
                    <div className="table-grid">
                      {tables
                        .filter((t) => {
                          const r = active.find((x) => x.table_id === t.id);
                          return (
                            filter === "all" ||
                            (filter === "idle" && !r) ||
                            (filter === "overdue" &&
                              r &&
                              now - r.received_at > 300) ||
                            (filter === "working" &&
                              (r?.state === "ASSIGNED" ||
                                r?.state === "ACCEPTED")) ||
                            r?.state === filter
                          );
                        })
                        .map((t) => {
                          const r = active.find((x) => x.table_id === t.id);
                          return (
                            <TableTile
                              key={t.id}
                              table={t}
                              request={r}
                              now={now}
                              staff={staffName(r?.staff_id ?? null)}
                              onClick={() => selectTable(t.id)}
                            />
                          );
                        })}
                    </div>
                    {!tables.length && (
                      <div className="empty">
                        <h3>Chưa đăng ký bàn</h3>
                        <p>Đăng ký node trước khi kết nối gateway.</p>
                        <button onClick={() => setPage("settings")}>
                          Mở cấu hình
                        </button>
                      </div>
                    )}
                    {tables.length > 0 &&
                      filter !== "all" &&
                      !tables.some((t) => {
                        const r = active.find((x) => x.table_id === t.id);
                        return filter === "idle"
                          ? !r
                          : filter === "overdue"
                            ? r && now - r.received_at > 300
                            : filter === "working"
                              ? r?.state === "ASSIGNED" ||
                                r?.state === "ACCEPTED"
                              : r?.state === filter;
                      }) && (
                        <div className="empty">
                          <p>Không có bàn phù hợp bộ lọc.</p>
                          <button onClick={() => setFilter("all")}>
                            Xem tất cả
                          </button>
                        </div>
                      )}
                    <footer className="grid-footer">
                      ◉ Đèn trên UI biểu thị nghiệp vụ. Trạng thái LED được xác
                      minh riêng tại chi tiết bàn.
                    </footer>
                  </section>
                  <aside className="queue">
                    <div className="grid-heading">
                      <h3>Hàng đợi phục vụ</h3>
                      <span className="count">{active.length}</span>
                    </div>
                    {!active.length ? (
                      <div className="empty compact">
                        <span>✓</span>
                        <h3>Tất cả đã sẵn sàng</h3>
                        <p>Yêu cầu mới sẽ xuất hiện tại đây.</p>
                        {data.mode === "simulation" && (
                          <button onClick={() => setPage("simulator")}>
                            Mở bàn mô phỏng
                          </button>
                        )}
                      </div>
                    ) : (
                      active.map((r) => (
                        <button
                          className="queue-item"
                          key={r.id}
                          onClick={() => selectTable(r.table_id)}
                        >
                          <div className="row">
                            <strong>{tableName(r.table_id)}</strong>
                            <time
                              className={
                                now - r.received_at > 300 ? "overdue-text" : ""
                              }
                            >
                              {duration(now - r.received_at)}
                            </time>
                          </div>
                          <div className="row">
                            <span className={`badge ${r.state}`}>
                              {labels[r.state]}
                            </span>
                            {now - r.received_at > 300 && (
                              <span className="overdue">Quá hạn</span>
                            )}
                          </div>
                          <small>{staffName(r.staff_id)}</small>
                        </button>
                      ))
                    )}
                    <div className="queue-footer">
                      <span>Đã hoàn tất</span>
                      <strong>{data.stats.completed}</strong>
                      <small>
                        TB phục vụ:{" "}
                        {data.stats.average_seconds === null
                          ? "Chưa có dữ liệu"
                          : duration(data.stats.average_seconds)}
                      </small>
                    </div>
                  </aside>
                </div>
              </>
            )}
            {page === "simulator" && data.mode === "simulation" && (
              <>
                <div className="section-heading">
                  <div>
                    <span className="eyebrow">
                      PHÒNG DEMO · DỮ LIỆU MÔ PHỎNG RIÊNG
                    </span>
                    <h2>Bàn mô phỏng</h2>
                    <p>
                      Nút tương tác gửi sự kiện vào backend và lưu SQLite thật.
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
                        value={selected ?? 1}
                        onChange={(e) => selectTable(Number(e.target.value))}
                      >
                        {tables
                          .filter((t) => t.enabled)
                          .map((t) => (
                            <option key={t.id} value={t.id}>
                              {t.name}
                            </option>
                          ))}
                      </select>
                    </label>
                    <SimNode
                      data={data}
                      nodeId={
                        tables.find((t) => t.id === (selected ?? 1))?.node_id ??
                        1
                      }
                      now={now}
                      disabled={pending}
                      send={sim}
                    />
                  </section>
                  <section className="faults">
                    <h3>Thử tình huống lỗi</h3>
                    <p>Các điều khiển này chỉ tồn tại trong mode mô phỏng.</p>
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
                        value={data.simulator?.fault ?? "none"}
                        onChange={(e) =>
                          void sim({ action: "fault", fault: e.target.value })
                        }
                      >
                        <option value="none">Không gây lỗi</option>
                        <option value="drop_event">Mất sự kiện một lần</option>
                        <option value="drop_receipt">
                          Mất receipt một lần
                        </option>
                        <option value="duplicate">Nhân đôi sự kiện</option>
                      </select>
                    </label>
                    <label>
                      Trễ CALL (giây)
                      <input
                        type="number"
                        min="0"
                        max="30"
                        value={data.simulator?.delay ?? 0}
                        onChange={(e) =>
                          void sim({
                            action: "delay",
                            seconds: Number(e.target.value),
                          })
                        }
                      />
                    </label>
                    <button
                      disabled={pending}
                      onClick={() =>
                        void sim({ action: "advance", seconds: 301 })
                      }
                    >
                      Tua +301 giây · chỉ clock demo
                    </button>
                    <small>
                      Thời gian chờ không reset khi xác nhận hoặc giao việc.
                      Poll mặc định {data.simulator?.poll_seconds}s; cửa sổ bấm
                      đúp {data.simulator?.double_ms}ms, chưa xác nhận firmware.
                    </small>
                    <button
                      className="danger-button"
                      disabled={pending}
                      onClick={() => {
                        if (
                          confirm(
                            "Xóa toàn bộ lịch sử và yêu cầu trong database DEMO?",
                          )
                        )
                          void sim({ action: "reset", confirm: "RESET DEMO" });
                      }}
                    >
                      Reset dữ liệu demo…
                    </button>
                  </section>
                </div>
              </>
            )}
            {page === "history" && (
              <HistoryView
                onDetail={(id) => {
                  setSelected(null);
                  setHistoryId(id);
                }}
                data={data}
              />
            )}
            {page === "settings" && (
              <Settings data={data} pending={pending} run={run} />
            )}
          </main>
        )}
        <footer className="app-footer">
          <span>
            TRUNG TÂM TẠI QUÁN ·{" "}
            {data.mode === "simulation"
              ? "DATABASE MÔ PHỎNG"
              : "DATABASE PHẦN CỨNG"}
          </span>
          <span>RF / pin / độ trễ thực tế: Chưa có dữ liệu</span>
        </footer>
      </div>
      {((selected !== null && page !== "simulator") || historyId) &&
        !staffPage && (
          <aside
            className="detail-panel"
            role="dialog"
            aria-label="Chi tiết bàn"
          >
            <div className="panel-heading">
              <div>
                <span className="eyebrow">CHI TIẾT YÊU CẦU</span>
                <h2>
                  {selectedTable?.name ??
                    (detail ? tableName(detail.request.table_id) : "Lịch sử")}
                </h2>
              </div>
              <button autoFocus aria-label="Đóng chi tiết" onClick={close}>
                ×
              </button>
            </div>
            {detailError ? (
              <div className="banner danger">
                {detailError}
                <button onClick={() => void loadDetail()}>Thử lại</button>
              </div>
            ) : detailId && !detail ? (
              <>
                <div className="skeleton" />
                <div className="skeleton" />
              </>
            ) : detail ? (
              <>
                <span className={`badge ${detail.request.state}`}>
                  {labels[detail.request.state]}
                </span>
                <h3>
                  Đã chờ{" "}
                  {duration(
                    (detail.request.completed_at ?? now) -
                      detail.request.received_at,
                  )}
                </h3>
                <p className="subtle">
                  Nhận lúc {stamp(detail.request.received_at)}
                </p>
                {selectedTable && (
                  <DeviceSync table={selectedTable} request={detail.request} />
                )}
                {detail.request.state === "WAITING_ACK" && (
                  <button
                    className="primary full"
                    disabled={pending}
                    onClick={() => void action(detail.request, "ack")}
                  >
                    {pending ? "Đang lưu…" : "Xác nhận yêu cầu"}
                  </button>
                )}
                {["ACKNOWLEDGED", "ASSIGNED", "ACCEPTED"].includes(
                  detail.request.state,
                ) && (
                  <label>
                    Giao cho nhân viên
                    <select
                      aria-label="Giao cho nhân viên"
                      disabled={pending}
                      value=""
                      onChange={(e) => {
                        if (
                          detail.request.state !== "ACCEPTED" ||
                          confirm(
                            "Nhân viên đã nhận. Xác nhận thu hồi và giao lại?",
                          )
                        )
                          void action(detail.request, "assign", {
                            staff_id: Number(e.target.value),
                            confirm_reassign:
                              detail.request.state === "ACCEPTED",
                          });
                      }}
                    >
                      <option value="">Chọn nhân viên khả dụng…</option>
                      {data.staff
                        .filter((s) => s.active && s.available)
                        .map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.name}
                          </option>
                        ))}
                    </select>
                  </label>
                )}
                {detail.request.staff_id && (
                  <div className="instruction">
                    {staffName(detail.request.staff_id)} · phiên{" "}
                    {detail.request.assignment_revision}
                    <br />
                    {detail.request.state === "ACCEPTED"
                      ? "Nhân viên đã nhận việc. Hoàn tất bằng nút ẩn tại bàn."
                      : "Đã giao. Chờ nhân viên nhận."}
                  </div>
                )}
                <h3>Giao thiết bị nhân viên</h3>
                {detail.assignments.map((a) => (
                  <p className="subtle" key={a.revision}>
                    Phiên {a.revision}:{" "}
                    {a.revoked_at
                      ? "Đã thu hồi"
                      : a.accepted_at
                        ? "Đã nhận việc"
                        : a.delivered_at
                          ? "Web prototype đã nhận thông báo"
                          : "Chưa gửi tới prototype"}
                  </p>
                ))}
                <h3>Lệnh xuống bàn</h3>
                <div className="command-list">
                  {detail.commands.map((c) => (
                    <div key={c.command_id}>
                      <strong>{c.type}</strong>
                      <small>
                        {commandStatus[c.status] ?? c.status} · thử {c.attempts}
                        /5{c.error ? ` · ${c.error}` : ""}
                      </small>
                    </div>
                  ))}
                </div>
                <h3>Nhật ký sự kiện</h3>
                <ol className="timeline">
                  {detail.events
                    .slice()
                    .reverse()
                    .map((e) => (
                      <li key={e.id}>
                        <strong>{eventLabels[e.type] ?? e.type}</strong>
                        <small>
                          {stamp(e.received_at)} ·{" "}
                          {resultLabels[e.result] ?? e.result}
                        </small>
                        {e.reason && (
                          <span className="overdue-text">{e.reason}</span>
                        )}
                      </li>
                    ))}
                </ol>
              </>
            ) : (
              <div className="empty">
                <h3>Bàn đang rảnh</h3>
                <p>
                  {selectedTable?.enabled
                    ? "Đang ngủ hoặc chưa có dữ liệu."
                    : "Bàn đã tắt sử dụng."}
                </p>
                {data.mode === "simulation" && (
                  <button onClick={() => setPage("simulator")}>
                    Mở nút mô phỏng
                  </button>
                )}
              </div>
            )}
          </aside>
        )}
    </div>
  );
}
function message(e: unknown) {
  return e instanceof z.ZodError
    ? "Dữ liệu trung tâm không đúng định dạng. Thử tải lại."
    : e instanceof Error
      ? e.message
      : "Không thể thực hiện. Vui lòng thử lại.";
}
function TableTile({
  table,
  request: r,
  now,
  staff,
  onClick,
}: {
  table: Table;
  request?: ServiceRequest;
  now: number;
  staff: string;
  onClick: () => void;
}) {
  return (
    <button
      className={`table-tile ${r?.state ?? "idle"} ${table.enabled ? "" : "disabled-table"}`}
      onClick={onClick}
      aria-label={`${table.name} — ${r ? labels[r.state] : "Bàn rảnh"}`}
    >
      <div className="row">
        <strong title={table.name}>{table.name}</strong>
        <span aria-hidden="true">{r ? "◉" : "○"}</span>
      </div>
      <span className="table-state">
        {r ? labels[r.state] : table.enabled ? "Bàn rảnh" : "Đã tắt"}
      </span>
      {r ? (
        <>
          <b className="wait">{duration(now - r.received_at)}</b>
          <small title={staff}>{staff}</small>
          {now - r.received_at > 300 && (
            <span className="overdue">◷ Quá 5 phút</span>
          )}
          <small className="sync-label">
            {table.observed_request_id === r.id &&
            table.observed_revision === r.version
              ? "✓ Bàn đã đồng bộ"
              : "↻ Chờ bàn đồng bộ"}
          </small>
        </>
      ) : (
        <>
          <span className="idle-line">—</span>
          <small>Đang ngủ / chưa có dữ liệu</small>
        </>
      )}
    </button>
  );
}
function DeviceSync({
  table,
  request: r,
}: {
  table: Table;
  request: ServiceRequest;
}) {
  const applied =
    table.observed_request_id === r.id && table.observed_revision === r.version;
  return (
    <div className="device-sync">
      <strong>
        {applied
          ? `LED báo cáo: ${table.led === "GREEN" ? "xanh" : table.led === "RED" ? "đỏ" : "tắt"}`
          : "Đang chờ bàn nhận"}
      </strong>
      <small>Lần cuối thấy: {stamp(table.last_seen)}</small>
      <small>
        Pin:{" "}
        {table.battery_mv === null
          ? "Chưa có dữ liệu"
          : `${table.battery_mv} mV`}
      </small>
    </div>
  );
}
function SimNode({
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
  send: (body: unknown) => Promise<void>;
}) {
  const n = data.simulator?.nodes.find((n) => n.node_id === nodeId),
    holding = n?.phase === "holding";
  const seconds =
    holding && n.hold_at !== null
      ? Math.min(5, Math.max(0, now - n.hold_at))
      : 0;
  const down = useRef(false);
  const release = () => {
    if (down.current) {
      down.current = false;
      void send({ action: "release", node_id: nodeId });
    }
  };
  useEffect(
    () => () => {
      if (down.current) {
        down.current = false;
        void api("/sim/action", { action: "release", node_id: nodeId });
      }
    },
    [nodeId],
  );
  return (
    <>
      <div
        className={`sim-led ${holding ? "blinking" : (n?.led ?? "OFF")}`}
        aria-label={`LED mô phỏng ${holding ? "đỏ nhấp nháy" : (n?.led ?? "OFF")}`}
      />
      <h3>
        {holding
          ? `Đang giữ ${seconds.toFixed(1)} / 5 giây`
          : n?.phase === "sending"
            ? "Đang gửi / chưa xác nhận"
            : n?.led === "GREEN"
              ? "Quản lý đã xác nhận · LED xanh"
              : n?.led === "RED"
                ? "Trung tâm đã lưu · LED đỏ"
                : "Đang ngủ · LED tắt"}
      </h3>
      <progress max="5" value={seconds} aria-label="Thời gian giữ nút" />
      <button
        className="call-button"
        disabled={
          disabled ||
          (!holding && n?.phase !== undefined && n.phase !== "sleep")
        }
        onPointerDown={(e) => {
          if (e.button !== 0) return;
          e.currentTarget.setPointerCapture(e.pointerId);
          down.current = true;
          void send({ action: "press", node_id: nodeId });
        }}
        onPointerUp={release}
        onPointerCancel={release}
        onLostPointerCapture={release}
        onKeyDown={(e) => {
          if ((e.key === " " || e.key === "Enter") && !e.repeat) {
            e.preventDefault();
            down.current = true;
            void send({ action: "press", node_id: nodeId });
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
        GIỮ ĐỂ GỌI<span>5 giây liên tục</span>
      </button>
      <p>
        Thả trước 5 giây để hủy. Đỏ sáng liên tục chỉ sau receipt từ trung tâm.
      </p>
      <button
        className="hidden-button"
        disabled={disabled || !n?.request_id}
        onClick={() => void send({ action: "hidden", node_id: nodeId })}
      >
        Nút ẩn · bấm hai lần để hoàn tất
      </button>
      <small>
        Hai lần bấm riêng trong cửa sổ {data.simulator?.double_ms}ms. Web nhân
        viên không có thao tác này.
      </small>
      {n?.error && <p className="overdue-text">{n.error}</p>}
    </>
  );
}
function HistoryView({
  data,
  onDetail,
}: {
  data: Snapshot;
  onDetail: (id: string) => void;
}) {
  const [history, setHistory] = useState<History | null>(null),
    [error, setError] = useState(""),
    [table, setTable] = useState(""),
    [staff, setStaff] = useState(""),
    [state, setState] = useState(""),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [offset, setOffset] = useState(0);
  const params = new URLSearchParams({ limit: "20", offset: String(offset) });
  if (table) params.set("table_id", table);
  if (staff) params.set("staff_id", staff);
  if (state) params.set("state", state);
  if (start)
    params.set("start", String(new Date(start + "+07:00").getTime() / 1000));
  if (end) params.set("end", String(new Date(end + "+07:00").getTime() / 1000));
  const query = params.toString();
  const load = useCallback(async () => {
    setError("");
    try {
      setHistory(historySchema.parse(await api("/history?" + query)));
    } catch (e) {
      setError(message(e));
    }
  }, [query]);
  useEffect(() => {
    setHistory(null);
    void load();
  }, [load]);
  return (
    <>
      <div className="section-heading">
        <div>
          <span className="eyebrow">DỮ LIỆU TỪ TRUNG TÂM</span>
          <h2>Lịch sử phục vụ</h2>
          <p>Mỗi dòng là một yêu cầu, lưu qua các lần khởi động.</p>
        </div>
        <a className="button" href={"/api/export.csv?" + query}>
          ↓ Xuất CSV
        </a>
      </div>
      <div className="history-filters">
        <label>
          Bàn
          <select
            value={table}
            onChange={(e) => {
              setTable(e.target.value);
              setOffset(0);
            }}
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
          Nhân viên
          <select
            value={staff}
            onChange={(e) => {
              setStaff(e.target.value);
              setOffset(0);
            }}
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
            onChange={(e) => {
              setState(e.target.value);
              setOffset(0);
            }}
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
            onChange={(e) => {
              setStart(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <label>
          Đến thời gian (VN)
          <input
            type="datetime-local"
            value={end}
            onChange={(e) => {
              setEnd(e.target.value);
              setOffset(0);
            }}
          />
        </label>
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
                  <th>Bàn</th>
                  <th>Trạng thái</th>
                  <th>Nhân viên</th>
                  <th>Trung tâm nhận</th>
                  <th>Hoàn tất</th>
                  <th>Chi tiết</th>
                </tr>
              </thead>
              <tbody>
                {history.items.map((r) => (
                  <tr key={r.id}>
                    <td>{r.table_name}</td>
                    <td>
                      <span className={`badge ${r.state}`}>
                        {labels[r.state]}
                      </span>
                    </td>
                    <td>{r.staff_name ?? "—"}</td>
                    <td>{stamp(r.received_at)}</td>
                    <td>{stamp(r.completed_at)}</td>
                    <td>
                      <button onClick={() => onDetail(r.id)}>Xem</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <span>
              {offset + 1}–{offset + history.items.length} / {history.total} yêu
              cầu
            </span>
            <button
              disabled={!offset}
              onClick={() => setOffset(Math.max(0, offset - 20))}
            >
              Trước
            </button>
            <button
              disabled={offset + 20 >= history.total}
              onClick={() => setOffset(offset + 20)}
            >
              Sau
            </button>
          </div>
        </>
      )}
    </>
  );
}
function Settings({
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
    [active, setActive] = useState(true),
    [available, setAvailable] = useState(true);
  return (
    <>
      <div className="section-heading">
        <div>
          <span className="eyebrow">THIẾT LẬP TẠI QUÁN</span>
          <h2>Bàn & nhân viên</h2>
          <p>Loopback prototype. Chưa hỗ trợ LAN hoặc truy cập Internet.</p>
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
            Node ID
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
            void run("/config/staff", { id: staffId, name, active, available });
          }}
        >
          <h3>Cấu hình nhân viên</h3>
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
      </div>
    </>
  );
}
