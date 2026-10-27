import type { Frame } from "../types";
export function Timeline({
  frame,
  count,
  playing,
  speed,
  onPlay,
  onIndex,
  onSpeed,
}: {
  frame: Frame;
  count: number;
  playing: boolean;
  speed: number;
  onPlay: () => void;
  onIndex: (index: number) => void;
  onSpeed: (speed: number) => void;
}) {
  return (
    <section className="timeline" aria-label="实验时间轴">
      <div className="timeline-top">
        <div className="play-controls">
          <button
            onClick={() => onIndex(Math.max(0, frame.index - 1))}
            disabled={frame.index === 0}
            aria-label="后退一步"
          >
            ←
          </button>
          <button className="primary" onClick={onPlay}>
            {playing ? "暂停" : "播放"}
          </button>
          <button
            onClick={() => onIndex(Math.min(count - 1, frame.index + 1))}
            disabled={frame.index === count - 1}
            aria-label="前进一步"
          >
            →
          </button>
          <select
            aria-label="播放速度"
            value={speed}
            onChange={(e) => onSpeed(Number(e.target.value))}
          >
            {[0.5, 1, 2, 4].map((n) => (
              <option value={n} key={n}>
                {n}×
              </option>
            ))}
          </select>
        </div>
        <div className="time-readout">
          <strong data-testid="current-step">STEP {frame.step}</strong>
          <span>
            {frame.index + 1} / {count} 帧 ·{" "}
            {frame.timestamp ||
              (frame.seconds === null ? "时间暂无数据" : `${frame.seconds} s`)}
          </span>
        </div>
      </div>
      <input
        aria-label="播放位置"
        type="range"
        min="0"
        max={count - 1}
        value={frame.index}
        onChange={(e) => onIndex(Number(e.target.value))}
      />
    </section>
  );
}
