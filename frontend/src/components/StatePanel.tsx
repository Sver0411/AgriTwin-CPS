import {
  channels,
  formatValue,
  labels,
  units,
  type Device,
  type Frame,
  type Run,
} from "../types";
export const stateLabel = (s: string | null) =>
  s === null
    ? "暂无数据"
    : {
        normal: "检查正常",
        suspected: "怀疑异常",
        confirmed_anomaly: "确认异常",
        unknown: "未知",
      }[s] || s;
const link = (v: boolean | null) =>
  v === null ? "暂无数据" : v ? "配置中断" : "配置在线";
export function StatePanel({ frame, run }: { frame: Frame; run: Run }) {
  return (
    <section className="state-grid" aria-label="当前温室状态">
      {channels.map((c) => {
        const v = frame.channels[c];
        return (
          <article className="state-card" key={c}>
            <div className="card-top">
              <span>{labels[c]}</span>
              <span className={`status ${v.state || "unknown"}`}>
                {stateLabel(v.state)}
              </span>
            </div>
            <div className="reading">
              {formatValue(v.estimated, units[c])}
              <small>模型估计</small>
            </div>
            <dl>
              {run.mode === "simulation" && (
                <>
                  <dt>仿真真值</dt>
                  <dd>{formatValue(v.truth, units[c])}</dd>
                </>
              )}
              {run.mode === "measurement" && (
                <>
                  <dt>源文件同刻测量</dt>
                  <dd>{formatValue(v.measured, units[c])}</dd>
                </>
              )}
              <dt>本步到达观测</dt>
              <dd>{formatValue(v.observed, units[c])}</dd>
              <dt>观测年龄</dt>
              <dd>
                {v.ageSteps === null
                  ? "暂无数据"
                  : `${v.ageSteps} 步${v.ageSeconds !== null ? ` / ${v.ageSeconds} s` : ""}`}
              </dd>
              <dt>启发式可信度</dt>
              <dd>{formatValue(v.trust)}</dd>
            </dl>
          </article>
        );
      })}
    </section>
  );
}
export function DeviceDetails({
  frame,
  run,
  selected,
}: {
  frame: Frame;
  run: Run;
  selected: Device;
}) {
  const sensor = channels.find((c) => c === selected);
  const value = sensor ? frame.channels[sensor] : null;
  const actuator = run.config.actuator as Record<string, unknown> | undefined;
  const related = run.events
    .filter(
      (e) =>
        e.index <= frame.index &&
        (e.channel === selected || (!sensor && e.kind === "actuator")),
    )
    .slice(-3)
    .reverse();
  return (
    <aside className="details">
      <h2>{labels[selected]}</h2>
      <p className="muted">当前记录 · STEP {frame.step}</p>
      {value && sensor ? (
        <>
          <dl>
            <dt>到达观测</dt>
            <dd>{formatValue(value.observed, units[sensor])}</dd>
            <dt>模型估计</dt>
            <dd>{formatValue(value.estimated, units[sensor])}</dd>
            <dt>观测生成时刻</dt>
            <dd>{value.observedTime || "暂无数据"}</dd>
            <dt>年龄</dt>
            <dd>
              {value.ageSteps === null ? "暂无数据" : `${value.ageSteps} 步`}
            </dd>
            <dt>可信度</dt>
            <dd>{formatValue(value.trust)}</dd>
            <dt>诊断状态</dt>
            <dd>{stateLabel(value.state)}</dd>
          </dl>
          <div className="reason">
            <small>实际诊断原因</small>
            <p>{value.reason || "暂无数据"}</p>
          </div>
        </>
      ) : (
        <dl>
          <dt>当前发出命令</dt>
          <dd>
            {formatValue(
              frame.commands[selected as "ventilation" | "irrigation"],
            )}
          </dd>
          <dt>当前实际动作</dt>
          <dd>
            {formatValue(
              frame.actual[selected as "ventilation" | "irrigation"],
            )}
          </dd>
          <dt>命令处理状态</dt>
          <dd>{frame.actuatorStatus || "暂无数据"}</dd>
          <dt>配置动作延迟</dt>
          <dd>
            {actuator?.delay_steps === undefined
              ? "暂无数据"
              : `${actuator.delay_steps} 步`}
          </dd>
          <dt>最小切换间隔</dt>
          <dd>
            {actuator?.min_interval_steps === undefined
              ? "暂无数据"
              : `${actuator.min_interval_steps} 步`}
          </dd>
        </dl>
      )}
      <div className="link-row">
        <span>本地 {link(frame.localOutage)}</span>
        <span>远程 {link(frame.remoteOutage)}</span>
      </div>
      <small>配置在线不保证交付成功；参见通信记录。</small>
      <h3>截至此刻的相关事件</h3>
      {related.length ? (
        related.map((e) => (
          <p className="mini-event" key={e.id}>
            STEP {e.step} · {e.title}
            <small>{e.detail}</small>
          </p>
        ))
      ) : (
        <p className="muted">暂无数据</p>
      )}
    </aside>
  );
}
