import { describe, it, expect, vi } from "vitest";
import { readFileSync } from "node:fs";
import { adapt, csv, indexAtStep, readFiles, loadDemo } from "./data";
import { formatValue } from "./types";
const trajectory =
  "step,time_seconds,true_temperature,observed_temperature,estimated_temperature,command_ventilation,actual_ventilation\n0,0,24,23,23.5,1,0\n2,120,25,,24.5,0,1\n";
const base = () => ({
  "trajectory.csv": trajectory,
  "config.yaml":
    "dt_seconds: 60\nsensor:\n  faults:\n    - start_step: 1\n      end_step: 3\n      channel: temperature\n      kind: missing\n",
});
describe("artifact adapter", () => {
  it("parses quoted CSV, missing fields and canonical units without zero filling", () => {
    expect(csv('a,b\n"x,y",2')[0].a).toBe("x,y");
    const run = adapt(base());
    expect(run.frames[1].channels.temperature.observed).toBeNull();
    expect(run.frames[0].channels.humidity.estimated).toBeNull();
    expect(formatValue(null, "°C")).toBe("暂无数据");
    expect(formatValue(0.42, "fraction")).toBe("0.420 fraction");
    expect(run.frames[0].commands.ventilation).toBe(1);
    expect(run.frames[0].actual.ventilation).toBe(0);
  });
  it("aligns evidence at receipt and jumps to the next recorded frame", () => {
    const run = adapt({
      ...base(),
      "health_events.csv":
        "step,channel,state,reason,trust\n2,temperature,suspected,delayed,0.3",
      "communication_events.csv":
        "link,generated_step,sent_step,scheduled_step,received_step,resolved_step,status\nlocal,0,0,2,2,2,delivered",
    });
    expect(run.frames[0].channels.temperature.state).toBeNull();
    expect(run.frames[1].channels.temperature.state).toBe("suspected");
    expect(run.events.find((e) => e.kind === "communication")?.index).toBe(1);
    expect(run.events.find((e) => e.kind === "configured")?.index).toBe(1);
    expect(indexAtStep(run.frames, 999)).toBe(1);
    expect(indexAtStep(run.frames, 0)).toBe(0);
  });
  it("does not create truth for measurement replay and preserves generated time", () => {
    const run = adapt({
      "trajectory.csv":
        "step,timestamp,measured_temperature,observed_temperature,observed_timestamp,estimated_temperature\n0,2025-01-01T00:00:00Z,20,,,23\n1,2025-01-01T00:05:00Z,21,20,2025-01-01T00:00:00Z,22",
    });
    expect(run.mode).toBe("measurement");
    expect(run.frames[1].channels.temperature.truth).toBeNull();
    expect(run.frames[1].channels.temperature.observedTime).toBe(
      "2025-01-01T00:00:00Z",
    );
    expect(run.frames[1].seconds).toBe(300);
    expect(() =>
      adapt({
        "trajectory.csv":
          trajectory.replace("true_temperature", "measured_temperature") +
          ",true_humidity",
      }),
    ).toThrow();
  });
  it("rejects malformed input, duplicate steps, misordered times and explicit incompatible units", () => {
    expect(() => adapt({})).toThrow("trajectory");
    expect(() => adapt({ "trajectory.csv": "step\n0\n0" })).toThrow("递增");
    expect(() =>
      adapt({ "trajectory.csv": "step,timestamp\n0,2025-01-02\n1,2025-01-01" }),
    ).toThrow("时间戳");
    expect(() =>
      adapt({ "trajectory.csv": trajectory.replace("24,23", "oops,23") }),
    ).toThrow("数值");
    expect(() =>
      adapt({
        ...base(),
        "schema.json": JSON.stringify({
          trajectory_units: { true_temperature: "F" },
        }),
      }),
    ).toThrow("单位");
  });
  it("propagates file failures and refuses blending runs", async () => {
    await expect(
      readFiles([
        {
          name: "trajectory.csv",
          text: async () => {
            throw new Error("read failed");
          },
        },
      ]),
    ).rejects.toThrow("read failed");
    await expect(
      readFiles([
        { name: "trajectory.csv", text: async () => trajectory },
        { name: "trajectory.csv", text: async () => trajectory },
      ]),
    ).rejects.toThrow("重复");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
    await expect(loadDemo()).rejects.toThrow("清单");
    vi.unstubAllGlobals();
  });
});

it("loads the actual bundled engine artifacts and joins a recorded frame", () => {
  const names: string[] = JSON.parse(
    readFileSync("public/demo/manifest.json", "utf8"),
  );
  const files = Object.fromEntries(
    names.map((name) => [name, readFileSync(`public/demo/${name}`, "utf8")]),
  );
  const run = adapt(files);
  const source = csv(files["trajectory.csv"]);
  expect(run.mode).toBe("simulation");
  expect(run.origin).toBe("synthetic proxy model");
  expect(run.frames).toHaveLength(96);
  expect(run.frames[35].channels.temperature.estimated).toBe(
    Number(source[35].estimated_temperature),
  );
  expect(run.frames[35].actual.irrigation).toBe(
    Number(source[35].actual_irrigation),
  );
  expect(run.frames[35].actuatorStatus).toBe("failed");
  expect(run.events.some((event) => event.kind === "estimator")).toBe(true);
});

it("uses actual elapsed seconds for irregular replay age", () => {
  const run = adapt({
    "trajectory.csv":
      "step,timestamp,measured_temperature,observed_temperature,observation_delay_seconds,observation_age_temperature_steps\n0,2025-01-01T00:00:00Z,20,,,\n1,2025-01-01T00:02:00Z,21,20,120,1",
    "config.yaml": "dt_seconds: 300",
  });
  expect(run.frames[1].channels.temperature.ageSeconds).toBe(120);
  expect(run.frames[1].channels.temperature.ageSteps).toBe(1);
});
