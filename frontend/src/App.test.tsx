import { afterEach, expect, it, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import App from "./App";
import { adapt } from "./data";
vi.mock("./components/Greenhouse", () => ({
  Greenhouse: ({
    frame,
    onSelect,
  }: {
    frame: { step: number };
    onSelect: (id: string) => void;
  }) => (
    <div>
      <span data-testid="scene-step">STEP {frame.step}</span>
      <button onClick={() => onSelect("ventilation")}>选择通风</button>
    </div>
  ),
}));
const fixture = adapt({
  "trajectory.csv":
    "step,time_seconds,true_temperature,estimated_temperature,command_ventilation,actual_ventilation,observed_temperature\n0,0,24,23,1,0,22\n1,60,25,24,0,1,\n2,120,26,25,0,0,24",
  "config.yaml":
    "dt_seconds: 60\nsensor:\n  faults:\n    - start_step: 2\n      end_step: 3\n      kind: missing\n      channel: temperature",
});
vi.mock("./data", async (original) => ({
  ...(await original<typeof import("./data")>()),
  loadDemo: vi.fn(async () => fixture),
}));
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
it("synchronizes scene, cards, details, cursor and event jump with a single index", async () => {
  render(<App />);
  fireEvent.click(screen.getByText("加载仿真示例"));
  await waitFor(() =>
    expect(screen.getByTestId("current-step").textContent).toBe("STEP 0"),
  );
  expect(screen.getByTestId("scene-step").textContent).toBe("STEP 0");
  expect(screen.getAllByText("23.00 °C").length).toBeGreaterThan(0);
  expect(screen.getAllByTestId("observation-point")).toHaveLength(2);
  const cursor = screen.getAllByTestId("chart-cursor")[0].getAttribute("x1");
  fireEvent.click(screen.getByLabelText("前进一步"));
  expect(screen.getByTestId("scene-step").textContent).toBe("STEP 1");
  expect(screen.getByTestId("current-step").textContent).toBe("STEP 1");
  expect(screen.getAllByText("24.00 °C").length).toBeGreaterThan(0);
  expect(screen.getAllByTestId("chart-cursor")[0].getAttribute("x1")).not.toBe(
    cursor,
  );
  fireEvent.click(screen.getByText("选择通风"));
  expect(screen.getByText("当前发出命令")).toBeTruthy();
  fireEvent.click(screen.getByText("传感器窗口开始"));
  expect(screen.getByTestId("current-step").textContent).toBe("STEP 2");
  expect(screen.getByTestId("scene-step").textContent).toBe("STEP 2");
  fireEvent.change(screen.getByLabelText("播放位置"), {
    target: { value: "0" },
  });
  expect(screen.getByTestId("scene-step").textContent).toBe("STEP 0");
  fireEvent.click(screen.getByText("播放"));
  await waitFor(
    () => expect(screen.getByTestId("current-step").textContent).toBe("STEP 1"),
    { timeout: 1500 },
  );
  fireEvent.click(screen.getByText("暂停"));
});
