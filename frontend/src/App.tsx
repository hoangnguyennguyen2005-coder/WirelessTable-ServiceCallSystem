import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  detailSchema,
  isOverdue,
  message,
  useLive,
  useNow,
  type Detail,
  type ServiceRequest,
} from "./api";
import { DetailPanel } from "./DetailPanel";
import { HistoryPage } from "./HistoryPage";
import { Overview, type Filter } from "./Overview";
import { SettingsPage } from "./SettingsPage";
import { SimulatorPage } from "./SimulatorPage";
import { StaffDevicePage } from "./StaffDevicePage";

type Page = "overview" | "simulator" | "history" | "settings";

export default function App() {
  const { data, error, connected, refresh } = useLive();
  const [page, setPage] = useState<Page>("overview"),
    [selected, setSelected] = useState<number | null>(null),
    [detail, setDetail] = useState<Detail | null>(null),
    [detailError, setDetailError] = useState(""),
    [pending, setPending] = useState(false),
    [notice, setNotice] = useState(""),
    [filter, setFilter] = useState<Filter>("all"),
    [sound, setSound] = useState(false),
    [historyId, setHistoryId] = useState<string | null>(null);
  const now = useNow(data?.now);
  const simQueue = useRef<Promise<void>>(Promise.resolve());
  const audio = useRef<AudioContext | null>(null),
    seen = useRef<Set<string>>(new Set()),
    initialized = useRef(false);
  const staffPage = location.pathname === "/staff";
  const selectedRequest = data?.requests.find((r) => r.table_id === selected);
  const selectedRequestId = selectedRequest?.id,
    selectedVersion = selectedRequest?.version;
  const detailSequence = useRef(0);
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
  // Audible reminder once per new request and once when it becomes overdue (ER-F08).
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
  const run = async (path: string, body: unknown) => {
    if (pending) return;
    setPending(true);
    setNotice("");
    try {
      await api(path, body);
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
    void run(`/requests/${r.id}/${kind}`, {
      expected_version: r.version,
      idempotency_key: crypto.randomUUID(),
      ...extra,
    });
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
  const overdue = data.requests.filter((r) => isOverdue(r, now, data.limits));
  const nav = (
    [
      ["overview", "▦", "Tổng quan"],
      ["simulator", "◎", "Bàn mô phỏng"],
      ["history", "◷", "Lịch sử"],
      ["settings", "⚙", "Cấu hình"],
    ] as const
  ).filter(([key]) => key !== "simulator" || data.mode === "simulation");
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
          {nav.map(([key, icon, label]) => (
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
            {(data.mode === "simulation" || data.staff_stub) && (
              <a href="/staff" className="staff-link">
                ↗ Thiết bị nhân viên (
                {data.mode === "simulation" ? "mô phỏng" : "stub"})
              </a>
            )}
            <p>Concept C · Hoạt động tại quán</p>
            <small>Pro Mini → nRF24 → Gateway USB</small>
          </div>
        </nav>
      )}
      <div className="workspace">
        <header className="topbar">
          <div>
            <span className="eyebrow">WIRELESS TABLE-SERVICE CALL SYSTEM</span>
            <h1>PBL4 — Gọi phục vụ</h1>
          </div>
          <div className="top-status">
            <span className={`mode ${data.mode}`}>
              {data.mode === "simulation" ? "MÔ PHỎNG" : "PHẦN CỨNG"}
            </span>
            <span className="subtle">Quán #{data.venue_id}</span>
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
            Gateway đang ngắt · yêu cầu đã lưu vẫn được giữ, bàn sẽ đối soát khi
            liên lạc lại. {data.gateway.error}
          </div>
        )}
        {!staffPage && overdue.length > 0 && (
          <div className="banner reminder" role="status">
            ◷ Nhắc: {overdue.length} yêu cầu chưa hoàn tất sau 5 phút ·{" "}
            {overdue
              .map(
                (r) =>
                  data.tables.find((t) => t.id === r.table_id)?.name ??
                  `Bàn ${r.table_id}`,
              )
              .join(", ")}
            <button
              onClick={() => {
                setPage("overview");
                setFilter("overdue");
              }}
            >
              Xem
            </button>
          </div>
        )}
        {notice && (
          <div className="banner danger" role="alert">
            {notice}
            <button onClick={() => setNotice("")}>Đóng</button>
          </div>
        )}
        {staffPage ? (
          <StaffDevicePage data={data} now={now} />
        ) : (
          <main>
            {page === "overview" && (
              <Overview
                data={data}
                now={now}
                filter={filter}
                setFilter={setFilter}
                sound={sound}
                toggleSound={toggleSound}
                onSelect={selectTable}
                onOpen={setPage}
              />
            )}
            {page === "simulator" && data.mode === "simulation" && (
              <SimulatorPage
                data={data}
                now={now}
                pending={pending}
                tableId={selected}
                onTable={selectTable}
                sim={sim}
              />
            )}
            {page === "history" && (
              <HistoryPage
                data={data}
                onDetail={(id) => {
                  setSelected(null);
                  setHistoryId(id);
                }}
              />
            )}
            {page === "settings" && (
              <SettingsPage data={data} pending={pending} run={run} />
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
          <span>Tầm phủ RF / tuổi thọ pin thực tế: Chưa có dữ liệu đo</span>
        </footer>
      </div>
      {((selected !== null && page !== "simulator") || historyId) &&
        !staffPage && (
          <DetailPanel
            data={data}
            now={now}
            table={data.tables.find((t) => t.id === selected)}
            detail={detail}
            detailId={detailId}
            error={detailError}
            pending={pending}
            onAction={action}
            onRetry={() => void loadDetail()}
            onClose={close}
            onSimulator={() => setPage("simulator")}
          />
        )}
    </div>
  );
}
