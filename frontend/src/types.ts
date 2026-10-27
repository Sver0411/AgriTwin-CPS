export const channels = ["temperature", "humidity", "moisture"] as const;
export type Channel = (typeof channels)[number];
export type Device = Channel | "ventilation" | "irrigation";
export const labels: Record<Device, string> = {
  temperature: "空气温度",
  humidity: "相对湿度",
  moisture: "土壤水分",
  ventilation: "通风设备",
  irrigation: "灌溉设备",
};
export const units: Record<Channel, string> = {
  temperature: "°C",
  humidity: "%RH",
  moisture: "fraction",
};
export type Row = Record<string, string>;
export type Evidence =
  | "configured"
  | "observation"
  | "diagnosis"
  | "communication"
  | "actuator"
  | "recovery"
  | "sampling"
  | "estimator";
export const eventLabels: Record<Evidence, string> = {
  configured: "配置窗口",
  observation: "生成观测 / 注入暴露",
  diagnosis: "诊断证据",
  communication: "通信记录",
  actuator: "执行器记录",
  recovery: "恢复记录",
  sampling: "采样记录",
  estimator: "估计器同化",
};
export interface ChannelValue {
  truth: number | null;
  measured: number | null;
  observed: number | null;
  estimated: number | null;
  trust: number | null;
  ageSteps: number | null;
  ageSeconds: number | null;
  observedTime: string | null;
  state: string | null;
  reason: string | null;
}
export interface Frame {
  index: number;
  step: number;
  seconds: number | null;
  timestamp: string | null;
  channels: Record<Channel, ChannelValue>;
  commands: Record<"ventilation" | "irrigation", number | null>;
  actual: Record<"ventilation" | "irrigation", number | null>;
  localOutage: boolean | null;
  remoteOutage: boolean | null;
  sampled: boolean | null;
  actuatorStatus: string | null;
}
export interface RunEvent {
  id: string;
  step: number;
  index: number;
  kind: Evidence;
  title: string;
  detail: string;
  channel?: string;
  record: Row;
}
export interface Run {
  frames: Frame[];
  events: RunEvent[];
  mode: "simulation" | "measurement";
  origin: string;
  dataset: string;
  seed: string;
  dtSeconds: number | null;
  config: Record<string, unknown>;
  metadata: Record<string, unknown>;
  files: string[];
  warnings: string[];
}
export const formatValue = (value: number | null, unit = "") =>
  value === null
    ? "暂无数据"
    : `${value.toFixed(unit === "fraction" ? 3 : 2)}${unit ? " " + unit : ""}`;
