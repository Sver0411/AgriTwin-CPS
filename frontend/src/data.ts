import Papa from "papaparse";
import { parse as parseYaml } from "yaml";
import {
  channels,
  type Channel,
  type Frame,
  type Row,
  type Run,
  type RunEvent,
  type Evidence,
} from "./types";

export function csv(text: string): Row[] {
  if (!text.trim()) return [];
  const parsed = Papa.parse<Row>(text.trim(), {
    header: true,
    skipEmptyLines: true,
    delimiter: ",",
  });
  if (parsed.errors.length)
    throw new Error(`CSV 格式错误：${parsed.errors[0].message}`);
  return parsed.data;
}
export function number(value: unknown): number | null {
  if (
    value === undefined ||
    value === null ||
    String(value).trim() === "" ||
    String(value).toLowerCase() === "nan"
  )
    return null;
  const n = Number(value);
  if (!Number.isFinite(n)) throw new Error(`非法数值：${String(value)}`);
  return n;
}
const bool = (v: string | undefined): boolean | null =>
  v === undefined || v === ""
    ? null
    : v.toLowerCase() === "true"
      ? true
      : v.toLowerCase() === "false"
        ? false
        : null;
const obj = (v: unknown): Record<string, unknown> =>
  v && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : {};
const json = (files: Record<string, string>, name: string) =>
  files[name] ? obj(JSON.parse(files[name])) : {};
export function indexAtStep(
  frames: Pick<Frame, "step">[],
  step: number,
): number {
  // First saved state at or after the event; clamp events outside the recorded horizon.
  let low = 0,
    high = frames.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (frames[middle].step < step) low = middle + 1;
    else high = middle;
  }
  return Math.min(low, frames.length - 1);
}
export function adapt(files: Record<string, string>): Run {
  if (!files["trajectory.csv"])
    throw new Error(
      "请选择同一次运行的 trajectory.csv，可同时选择事件文件和 config.yaml。",
    );
  const rows = csv(files["trajectory.csv"]);
  if (!rows.length) throw new Error("trajectory.csv 没有数据。");
  if (!("step" in rows[0])) throw new Error("trajectory.csv 缺少 step 字段。");
  const config = files["config.yaml"]
    ? obj(parseYaml(files["config.yaml"]))
    : {};
  const metadata = json(files, "metadata.json");
  const schema = json(files, "schema.json");
  const replay =
    metadata.closed_loop_validation === false ||
    Boolean(files["replay.json"]) ||
    rows.some((r) => Object.keys(r).some((k) => k.startsWith("measured_")));
  const hasTruth = rows.some((r) =>
    Object.keys(r).some((k) => k.startsWith("true_")),
  );
  if (replay && hasTruth)
    throw new Error("来源冲突：测量回放不能同时声明仿真真值。");
  const dt = number(config.dt_seconds);
  const warnings: string[] = [];
  if (!dt)
    warnings.push("缺少时间步配置：仅显示已记录的时间，不将步数换算为秒。");
  if (!files["metadata.json"])
    warnings.push("缺少 metadata.json：来源与随机种子不可追溯。");
  const health = files["health_events.csv"]
    ? csv(files["health_events.csv"])
    : [];
  const healthMap = new Map(health.map((h) => [`${h.step}:${h.channel}`, h]));
  const actions = files["actuator_events.csv"]
    ? csv(files["actuator_events.csv"])
    : [];
  const actionMap = new Map(actions.map((a) => [a.execution_step, a]));
  const sourceTimes = new Map(
    rows.map((row) => [number(row.step), row.timestamp]),
  );
  let previous = -Infinity,
    previousTime = -Infinity;
  const frames: Frame[] = rows.map((r, index) => {
    const step = number(r.step);
    if (
      step === null ||
      !Number.isInteger(step) ||
      step < 0 ||
      step <= previous
    )
      throw new Error("step 必须非负、唯一且递增。");
    previous = step;
    const timestamp = r.state_timestamp || r.timestamp || null;
    if (timestamp) {
      const t = Date.parse(timestamp);
      if (!Number.isFinite(t) || t <= previousTime)
        throw new Error("时间戳必须有效、唯一且递增。");
      previousTime = t;
    }
    const seconds =
      number(r.time_seconds) ??
      (timestamp
        ? (Date.parse(timestamp) -
            Date.parse(rows[0].state_timestamp || rows[0].timestamp)) /
          1000
        : dt
          ? step * dt
          : null);
    const channelValues = Object.fromEntries(
      channels.map((c) => {
        const h = healthMap.get(`${step}:${c}`);
        const observed = number(r[`observed_${c}`]);
        const generated = number(r[`observed_timestamp_${c}_step`]);
        const observedTime =
          observed === null
            ? null
            : r.observed_timestamp ||
              (generated !== null ? `step ${generated}` : null);
        const ageSteps = number(
          r[`observation_age_${c}_steps`] ?? h?.age_steps,
        );
        const sourceStep = number(h?.generated_step);
        const sourceTime =
          sourceStep !== null ? sourceTimes.get(sourceStep) : null;
        const ageSeconds = replay
          ? observed !== null
            ? number(r.observation_delay_seconds)
            : timestamp && sourceTime
              ? (Date.parse(timestamp) - Date.parse(sourceTime)) / 1000
              : null
          : ageSteps !== null && dt !== null
            ? ageSteps * dt
            : null;
        return [
          c,
          {
            truth: replay ? null : number(r[`true_${c}`]),
            measured: number(r[`measured_${c}`]),
            observed,
            estimated: number(r[`estimated_${c}`]),
            trust: number(r[`trust_${c}`] ?? h?.trust),
            ageSteps,
            ageSeconds,
            observedTime,
            state: h?.state || null,
            reason: h?.reason || null,
          },
        ];
      }),
    ) as Frame["channels"];
    return {
      index,
      step,
      seconds,
      timestamp,
      channels: channelValues,
      commands: {
        ventilation: number(r.command_ventilation),
        irrigation: number(r.command_irrigation),
      },
      actual: {
        ventilation: number(r.actual_ventilation),
        irrigation: number(r.actual_irrigation),
      },
      localOutage: bool(r.local_outage),
      remoteOutage: bool(r.remote_outage),
      sampled: bool(r.sampled),
      actuatorStatus: actionMap.get(r.step)?.status || null,
    };
  });
  // Units are canonical for this engine. Conflicting explicit schemas must not be relabelled.
  const declared = obj(schema.trajectory_units);
  for (const c of channels)
    for (const prefix of ["true", "estimated", "observed", "measured"]) {
      const unit = declared[`${prefix}_${c}`];
      if (
        unit &&
        !(c === "temperature"
          ? String(unit).includes("degC")
          : c === "humidity"
            ? String(unit).includes("%RH")
            : String(unit).includes("fraction"))
      )
        throw new Error(`不支持的单位 ${prefix}_${c}: ${String(unit)}`);
    }
  if (!files["schema.json"])
    warnings.push(
      "单位采用 AgriTwin 标准：°C、%RH、土壤水分 fraction；外部 CSV 请先经 Python 导入器转换。",
    );
  const events: RunEvent[] = [];
  const add = (
    kind: Evidence,
    step: number | null,
    title: string,
    detail: string,
    record: Row = {},
    channel?: string,
  ) => {
    if (step === null) return;
    events.push({
      id: `${kind}-${events.length}`,
      step,
      index: indexAtStep(frames, step),
      kind,
      title,
      detail,
      record,
      channel,
    });
  };
  const sensor = obj(config.sensor),
    communication = obj(config.communication);
  for (const [name, windows] of [
    ["传感器", sensor.faults],
    ["本地链路", obj(communication.local).outages],
    ["远程链路", obj(communication.remote).outages],
    ["执行器", obj(config.actuator).failures],
  ] as const) {
    if (Array.isArray(windows))
      for (const w of windows) {
        const a = obj(w);
        add(
          "configured",
          number(a.start_step),
          `${name}窗口开始`,
          `${String(a.kind || "中断")} · [${a.start_step}, ${a.end_step}) · 按步数`,
          {},
          String(a.channel || ""),
        );
        add(
          "configured",
          number(a.end_step),
          `${name}窗口结束`,
          "仅为配置边界，不代表已恢复",
        );
      }
  }
  for (const r of rows)
    for (const c of channels)
      if (
        bool(r[`fault_label_${c}`]) === true ||
        bool(r[`sensor_missing_${c}`]) === true
      )
        add(
          "observation",
          number(r.step),
          `${c} 生成时故障暴露`,
          "仿真注入标签，不是诊断结果",
          r,
          c,
        );
  const lastHealth = new Map<string, string>();
  for (const h of health) {
    const signature = `${h.state}/${h.reason}`;
    if (signature !== lastHealth.get(h.channel) && h.state !== "normal")
      add(
        "diagnosis",
        number(h.step),
        `${h.channel}: ${h.state}`,
        h.reason,
        h,
        h.channel,
      );
    lastHealth.set(h.channel, signature);
  }
  for (const e of files["communication_events.csv"]
    ? csv(files["communication_events.csv"])
    : []) {
    // Delivery/failure is only revealed at resolution, never at generation time.
    add(
      "communication",
      number(e.received_step) ?? number(e.resolved_step) ?? number(e.sent_step),
      `${e.link}: ${e.status}`,
      `生成 ${e.generated_step} → 计划 ${e.scheduled_step} → 接收 ${e.received_step || "—"}；${e.status === "pending_at_horizon" ? "结束时仍待处理" : "已记录状态"}`,
      e,
    );
  }
  for (const e of files["estimator_events.csv"]
    ? csv(files["estimator_events.csv"])
    : []) {
    const channel = channels[Number(e.channel_index)];
    if (e.channel_index === "") continue;
    add(
      "estimator",
      number(e.received_step),
      `${channel || "观测"}: ${bool(e.assimilated) ? "已同化" : "未同化"}`,
      `${e.reason} · 生成 ${e.generated_step} · 更新目标 ${e.target_step || "—"} · R ${e.effective_variance || "—"} / gain ${e.effective_gain || "—"}`,
      e,
      channel,
    );
  }
  for (const e of actions)
    if (e.status !== "applied")
      add(
        "actuator",
        number(e.execution_step),
        `执行命令 ${e.status}`,
        `请求通风 ${e.ventilation} / 灌溉 ${e.irrigation}；实际 ${e.actual_ventilation || "—"} / ${e.actual_irrigation || "—"}`,
        e,
      );
  for (const e of files["sampling_events.csv"]
    ? csv(files["sampling_events.csv"])
    : [])
    if (bool(e.sampled))
      add(
        "sampling",
        number(e.step),
        "采样执行",
        e.reason || e.reasons || "已记录采样",
        e,
      );
  for (const e of files["recovery_events.csv"]
    ? csv(files["recovery_events.csv"])
    : []) {
    const remote = e.kind === "remote";
    const delay = number(
      remote ? e.remote_resync_seconds : e.estimation_recovery_seconds,
    );
    const recovered = delay !== null && dt !== null;
    add(
      "recovery",
      recovered
        ? Number(e.end_step) + delay / dt
        : number(e.observation_stop_step),
      `${e.kind} ${recovered ? "观察到恢复" : "未观察到恢复 / 截尾"}`,
      remote
        ? "遥测重新同步；不是本地估计恢复"
        : "估计误差达到配置容差及驻留要求",
      e,
    );
  }
  events.sort((a, b) => a.step - b.step);
  return {
    frames,
    events,
    mode: replay ? "measurement" : "simulation",
    origin: String(metadata.data_origin || "来源未记录"),
    dataset: String(metadata.dataset_id || config.name || "已加载运行"),
    seed: String(metadata.seed ?? "暂无数据"),
    dtSeconds: dt,
    config,
    metadata,
    files: Object.keys(files),
    warnings,
  };
}
export async function readFiles(
  files: Iterable<Pick<File, "name" | "text">>,
): Promise<Run> {
  const contents: Record<string, string> = {};
  for (const file of files) {
    if (contents[file.name] !== undefined)
      throw new Error(`文件名重复：${file.name}。请选择单次运行。`);
    contents[file.name] = await file.text();
  }
  return adapt(contents);
}
export async function loadDemo(): Promise<Run> {
  const response = await fetch("/demo/manifest.json");
  if (!response.ok) throw new Error("演示清单读取失败");
  const names: string[] = await response.json();
  const files: Record<string, string> = {};
  for (const name of names) {
    const r = await fetch(`/demo/${name}`);
    if (!r.ok) throw new Error(`演示文件读取失败：${name}`);
    files[name] = await r.text();
  }
  return adapt(files);
}
