import {
  channels,
  labels,
  units,
  type Channel,
  type Frame,
  type Run,
} from "../types";
const colors: Record<string, string> = {
  truth: "#313a35",
  measured: "#8e6851",
  observed: "#9ba5a0",
  estimated: "#437a98",
  trust: "#557761",
  sampling: "#343b36",
  local: "#b68147",
  remote: "#757b9d",
};
function Chart({
  run,
  index,
  title,
  unit,
  series,
}: {
  run: Run;
  index: number;
  title: string;
  unit: string;
  series: { key: string; label: string; value: (f: Frame) => number | null }[];
}) {
  const available = series.filter((s) =>
    run.frames.some((f) => s.value(f) !== null),
  );
  const values = available.flatMap((s) =>
    run.frames.flatMap((f) => (s.value(f) === null ? [] : [s.value(f)!])),
  );
  let low = values.length
      ? values.reduce((a, b) => Math.min(a, b), Infinity)
      : 0,
    high = values.length
      ? values.reduce((a, b) => Math.max(a, b), -Infinity)
      : 1;
  if (high === low) {
    low -= 0.1;
    high += 0.1;
  }
  const pad = (high - low) * 0.1;
  low -= pad;
  high += pad;
  const x = (i: number) => 42 + (i / Math.max(run.frames.length - 1, 1)) * 548;
  const y = (v: number) => 145 - ((v - low) / (high - low)) * 115;
  const path = (value: (f: Frame) => number | null) => {
    let gap = true;
    return run.frames
      .map((f, i) => {
        const v = value(f);
        if (v === null) {
          gap = true;
          return "";
        }
        const segment = `${gap ? "M" : "L"}${x(i).toFixed(2)},${y(v).toFixed(2)}`;
        gap = false;
        return segment;
      })
      .join(" ");
  };
  return (
    <article className="chart">
      <div className="card-top">
        <h3>{title}</h3>
        <small>{unit}</small>
      </div>
      {available.length ? (
        <>
          <svg
            viewBox="0 0 610 170"
            role="img"
            aria-label={`${title}趋势，当前 STEP ${run.frames[index].step}`}
          >
            <line x1="42" x2="590" y1="145" y2="145" stroke="#ddd" />
            <text x="3" y="35">
              {high.toFixed(2)}
            </text>
            <text x="3" y="145">
              {low.toFixed(2)}
            </text>
            {available.map((s) => (
              <path
                key={s.key}
                d={path(s.value)}
                fill="none"
                stroke={colors[s.key]}
                strokeWidth={s.key === "estimated" ? 2.3 : 1.4}
                strokeDasharray={s.key === "observed" ? "3 3" : undefined}
              />
            ))}
            {available
              .filter((s) => s.key === "observed")
              .flatMap((s) =>
                run.frames.flatMap((frame, i) => {
                  const value = s.value(frame);
                  return value === null
                    ? []
                    : [
                        <circle
                          data-testid="observation-point"
                          key={`${s.key}-${i}`}
                          cx={x(i)}
                          cy={y(value)}
                          r="1.8"
                          fill={colors[s.key]}
                        />,
                      ];
                }),
              )}
            <line
              data-testid="chart-cursor"
              x1={x(index)}
              x2={x(index)}
              y1="20"
              y2="150"
              stroke="#111"
              strokeWidth="1"
            />
            <circle cx={x(index)} cy="155" r="3" fill="#111" />
          </svg>
          <div className="legend">
            {available.map((s) => (
              <span key={s.key}>
                <i style={{ background: colors[s.key] }} />
                {s.label}
              </span>
            ))}
          </div>
        </>
      ) : (
        <p className="no-data">暂无数据</p>
      )}
    </article>
  );
}
export function Trends({
  run,
  index,
  selected,
}: {
  run: Run;
  index: number;
  selected: string;
}) {
  const stateSeries = (c: Channel) => [
    ...(run.mode === "simulation"
      ? [
          {
            key: "truth",
            label: "仿真真值",
            value: (f: Frame) => f.channels[c].truth,
          },
        ]
      : [
          {
            key: "measured",
            label: "源文件同刻测量",
            value: (f: Frame) => f.channels[c].measured,
          },
        ]),
    {
      key: "observed",
      label: "到达观测（横轴为到达帧）",
      value: (f: Frame) => f.channels[c].observed,
    },
    {
      key: "estimated",
      label: "模型估计",
      value: (f: Frame) => f.channels[c].estimated,
    },
  ];
  const ordered = [...channels].sort((a, b) =>
    a === selected ? -1 : b === selected ? 1 : 0,
  );
  return (
    <section className="trends">
      <div className="section-title">
        <div>
          <h2>实验曲线</h2>
        </div>
        <p>竖线为当前时间，断点表示缺失数据</p>
      </div>
      <div className="chart-grid">
        {ordered.map((c) => (
          <Chart
            run={run}
            index={index}
            key={c}
            title={labels[c]}
            unit={units[c]}
            series={stateSeries(c)}
          />
        ))}
        <Chart
          run={run}
          index={index}
          title="传感器可信度"
          unit="启发式 [0,1]"
          series={channels.map((c, i) => ({
            key: ["trust", "estimated", "remote"][i],
            label: labels[c],
            value: (f) => f.channels[c].trust,
          }))}
        />
        <Chart
          run={run}
          index={index}
          title="采样与配置通信中断"
          unit="布尔：1 是，0 否"
          series={[
            {
              key: "sampling",
              label: "实际采样",
              value: (f) => (f.sampled === null ? null : Number(f.sampled)),
            },
            {
              key: "local",
              label: "本地配置中断",
              value: (f) =>
                f.localOutage === null ? null : Number(f.localOutage),
            },
            {
              key: "remote",
              label: "远程配置中断",
              value: (f) =>
                f.remoteOutage === null ? null : Number(f.remoteOutage),
            },
          ]}
        />
        <Chart
          run={run}
          index={index}
          title="执行器：命令与实际"
          unit="归一化 [0,1]"
          series={[
            {
              key: "local",
              label: "灌溉命令",
              value: (f) => f.commands.irrigation,
            },
            {
              key: "estimated",
              label: "实际灌溉",
              value: (f) => f.actual.irrigation,
            },
            {
              key: "remote",
              label: "通风命令",
              value: (f) => f.commands.ventilation,
            },
            {
              key: "truth",
              label: "实际通风",
              value: (f) => f.actual.ventilation,
            },
          ]}
        />
      </div>
    </section>
  );
}
