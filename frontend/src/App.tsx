import { useEffect, useRef, useState } from "react";
import { loadDemo, readFiles } from "./data";
import type { Device, Run } from "./types";
import { Greenhouse } from "./components/Greenhouse";
import { Timeline } from "./components/Timeline";
import { StatePanel, DeviceDetails } from "./components/StatePanel";
import { Trends } from "./components/Trends";
import { Events } from "./components/Events";
export default function App() {
  const [run, setRun] = useState<Run | null>(null),
    [index, setIndex] = useState(0),
    [playing, setPlaying] = useState(false),
    [speed, setSpeed] = useState(1),
    [selected, setSelected] = useState<Device>("temperature"),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false),
    [source, setSource] = useState("");
  const input = useRef<HTMLInputElement>(null);
  async function load(operation: () => Promise<Run>, label: string) {
    setLoading(true);
    setError("");
    setPlaying(false);
    try {
      const result = await operation();
      setRun(result);
      setIndex(0);
      setSource(label);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }
  const seek = (next: number) => {
    setPlaying(false);
    setIndex(next);
  };
  useEffect(() => {
    if (!playing || !run) return;
    const id = window.setInterval(
      () =>
        setIndex((i) => {
          if (i >= run.frames.length - 1) {
            setPlaying(false);
            return i;
          }
          return i + 1;
        }),
      700 / speed,
    );
    return () => clearInterval(id);
  }, [playing, speed, run]);
  const frame = run?.frames[index];
  return (
    <>
      <header>
        <a className="brand" href="#">
          AGRI<span>TWIN</span>
          <sup>CPS</sup>
        </a>
        <span className="header-label">实验记录 · 三维回放</span>
        <a href="http://127.0.0.1:8501/" target="_blank" rel="noreferrer">
          科研实验室 ↗
        </a>
      </header>
      <main>
        <section className="intro">
          <div>
            <h1>温室实验回放</h1>
            <p>加载实验结果，查看三维温室、状态曲线、故障和控制动作。</p>
          </div>
          <div className="load-box">
            <h2>加载数据</h2>
            <p>
              选择单次运行的
              trajectory.csv，及同目录的配置、元数据和事件文件。文件仅在本地浏览器中解析。
            </p>
            <div className="load-actions">
              <button
                className="primary"
                disabled={loading}
                onClick={() => input.current?.click()}
              >
                加载实验文件
              </button>
              <button
                disabled={loading}
                onClick={() => load(loadDemo, "内置仿真演示")}
              >
                加载仿真示例
              </button>
            </div>
            <input
              ref={input}
              aria-label="选择实验文件"
              type="file"
              multiple
              accept=".csv,.yaml,.json"
              hidden
              onChange={(e) => {
                const files = Array.from(e.target.files || []);
                if (files.length)
                  void load(() => readFiles(files), "本地实验文件");
                e.target.value = "";
              }}
            />
            <details>
              <summary>支持的文件</summary>
              <p>
                必选 trajectory.csv；建议同时选择
                config.yaml、metadata.json、schema.json。可选同目录的健康、通信、执行器、采样、恢复和估计器事件
                CSV。
              </p>
            </details>
          </div>
        </section>
        {loading && (
          <p role="status" className="notice">
            正在解析实验产物…
          </p>
        )}
        {error && (
          <p role="alert" className="error">
            加载失败：{error}
            {run ? " 保留上一份可用运行。" : ""}
          </p>
        )}
        {run && frame ? (
          <>
            <section className="run-bar">
              <div>
                <h2>
                  {source}{" "}
                  <span className="pill">
                    {run.mode === "simulation" ? "软件仿真" : "测量一致性回放"}
                  </span>
                </h2>
                <p>
                  {run.frames.length} 帧 · 随机种子 {run.seed}
                </p>
              </div>
              <details>
                <summary>数据来源与配置</summary>
                <pre>
                  {JSON.stringify(
                    {
                      dataset: run.dataset,
                      origin: run.origin,
                      files: run.files,
                      metadata: run.metadata,
                      config: run.config,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
            </section>
            {run.warnings.map((w) => (
              <p className="notice" key={w}>
                {w}
              </p>
            ))}
            <StatePanel frame={frame} run={run} />
            <div className="workspace">
              <Greenhouse
                frame={frame}
                selected={selected}
                onSelect={setSelected}
              />
              <DeviceDetails frame={frame} run={run} selected={selected} />
            </div>
            <Timeline
              frame={frame}
              count={run.frames.length}
              playing={playing}
              speed={speed}
              onPlay={() => {
                if (index === run.frames.length - 1) setIndex(0);
                setPlaying(!playing);
              }}
              onIndex={seek}
              onSpeed={setSpeed}
            />
            <Trends run={run} index={index} selected={selected} />
            <Events run={run} index={index} onJump={seek} />
          </>
        ) : (
          !loading && (
            <section className="empty">
              <p>尚未加载数据。内置示例为软件仿真，不是真实温室测量。</p>
            </section>
          )
        )}
        <footer>
          <strong>AgriTwin-CPS</strong>
          <p>离线结果查看器 · 实验配置与运行请使用科研实验室</p>
        </footer>
      </main>
    </>
  );
}
