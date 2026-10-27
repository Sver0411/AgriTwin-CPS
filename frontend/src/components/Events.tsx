import { useState } from "react";
import { eventLabels, type Evidence, type Run } from "../types";
export function Events({
  run,
  index,
  onJump,
}: {
  run: Run;
  index: number;
  onJump: (index: number) => void;
}) {
  const [filter, setFilter] = useState<Evidence | "all">("all");
  const filtered = run.events.filter(
    (e) => filter === "all" || filter === e.kind,
  );
  // Keep the nearest future and past records visible without mounting thousands of rows.
  const anchor = filtered.findIndex((e) => e.index >= index);
  const start = Math.max(0, (anchor < 0 ? filtered.length : anchor) - 4);
  return (
    <section className="events">
      <div className="section-title">
        <div>
          <h2>事件记录</h2>
        </div>
        <select
          aria-label="事件类型"
          value={filter}
          onChange={(e) => setFilter(e.target.value as Evidence | "all")}
        >
          <option value="all">全部类型 · {run.events.length}</option>
          {Object.entries(eventLabels).map(([key, label]) => (
            <option value={key} key={key}>
              {label}
            </option>
          ))}
        </select>
      </div>
      <div className="event-key">
        {Object.entries(eventLabels).map(([key, label]) => (
          <span className={`event-badge ${key}`} key={key}>
            {label}
          </span>
        ))}
      </div>
      <div className="event-list">
        {filtered.slice(start, start + 16).map((e) => (
          <button
            key={e.id}
            className={`event ${e.index === index ? "current" : ""}`}
            onClick={() => onJump(e.index)}
          >
            <span className={`event-dot ${e.kind}`} />
            <span className="event-time">STEP {e.step}</span>
            <span>
              <strong>{e.title}</strong>
              <small>{e.detail}</small>
            </span>
            <span className="jump">跳转 ↗</span>
          </button>
        ))}
        {!filtered.length && <p className="no-data">暂无数据</p>}
      </div>
      <small>
        显示当前时间附近的事件，点击跳转。配置窗口不代表已检测或已恢复。
      </small>
    </section>
  );
}
