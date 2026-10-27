"""Research workspaces backed exclusively by saved core simulation/replay artifacts."""

import hashlib
import io
import json
import traceback
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from agritwin_cps.config import SimulationConfig, load_config
from agritwin_cps.data_io.csv_import import ImportConfig, import_csv, load_data_config
from agritwin_cps.data_io.replay import ReplayConfig, write_replay
from agritwin_cps.experiments.adaptive import (
    ADAPTIVE_EXPERIMENTS,
    run_adaptive_experiment,
    variants,
)
from agritwin_cps.models.greenhouse import CHANNELS
from agritwin_cps.simulation.runner import write_json
from agritwin_cps.ui.workspace import ESTIMATORS, experiment_archive


def unique_target(root: Path, category: str) -> Path:
    return root / category / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:6])


def run_action(action, root: Path):
    """Single UI execution boundary: preserve previous success and persist failure diagnostics."""
    try:
        value = action()
    except Exception as exc:
        failure = {"error": str(exc), "traceback": traceback.format_exc()}
        st.session_state.adaptive_failure = failure
        target = unique_target(root, "failures")
        target.mkdir(parents=True)
        write_json(target / "failure.json", failure)
        st.error(f"执行失败，保留上次成功结果：{exc}")
        return None
    st.session_state.pop("adaptive_failure", None)
    return value


def failure_details():
    if st.session_state.get("adaptive_failure"):
        with st.expander("最近一次失败诊断"):
            st.code(st.session_state.adaptive_failure["traceback"])
            st.download_button(
                "下载失败诊断",
                json.dumps(st.session_state.adaptive_failure, indent=2),
                "failure.json",
                "application/json",
            )


def export_artifacts(directory: Path, key: str):
    st.caption(f"结果目录：{directory}")
    for filename in (
        "trajectory.csv",
        "metrics.json",
        "config.yaml",
        "data_config.yaml",
        "health_events.csv",
        "sampling_events.csv",
        "estimator_events.csv",
        "base_config.yaml",
        "per_seed.csv",
        "summary.csv",
        "measurement_per_seed.csv",
        "measurement_summary.csv",
    ):
        path = directory / filename
        if path.exists():
            st.download_button(filename, path.read_bytes(), filename, key=f"{key}_{filename}")
    if st.button("准备完整结果 ZIP", key=f"{key}_prepare"):
        st.session_state[f"{key}_archive"] = (str(directory), experiment_archive(directory))
    archive = st.session_state.get(f"{key}_archive")
    if archive and archive[0] == str(directory):
        st.download_button("下载完整 ZIP", archive[1], f"{directory.name}.zip", key=f"{key}_zip")


def trust_sampling(snapshot):
    from agritwin_cps.ui.views import select_run, show_figure

    st.subheader("传感器可信度与自适应采样")
    if snapshot is None:
        st.info("先在 Simulation Lab 运行实验，再查看实际记录。")
        return
    run = select_run(snapshot, "trust_run")
    result, frame = run.result, run.result.trajectory
    st.caption(
        f"估计器：{run.config.estimator.method} · 采样：{run.config.sampling.strategy}"
        f" · seed {run.seed}"
    )
    if result.health_events.empty:
        st.info("此历史结果未记录 2.0 健康与采样事件，请重新运行。")
        return
    tab = st.radio(
        "分析内容",
        ["传感器健康", "采样与传输", "协方差与历史回放"],
        horizontal=True,
        key="trust_view",
    )
    if tab == "传感器健康":
        channel = st.selectbox("通道", CHANNELS, key="trust_channel")
        health = result.health_events[result.health_events.channel == channel]
        st.dataframe(health.tail(1), hide_index=True, width="stretch")
        fig, axes = plt.subplots(2, 1, figsize=(10, 5), sharex=True)
        hours = health.step * run.config.dt_seconds / 3600
        axes[0].plot(hours, health.residual, color="#1D1D1F")
        axes[0].set_ylabel("Residual (channel units)")
        axes[1].step(hours, health.trust, where="post", color="#0071E3")
        axes[1].set_ylabel("Heuristic trust [0,1]")
        axes[1].set_ylim(-0.05, 1.05)
        axes[1].set_xlabel("Simulation time (h)")
        show_figure(fig)
        st.caption(
            "confirmed_anomaly 确认的是观测异常证据，不证明传感器故障原因。模型失配也可触发告警。"
            "baseline/EKF 记录健康但不使用可信度权重；trust_ekf 调整 R 或拒绝更新。"
        )
        st.dataframe(health, hide_index=True, height=280, width="stretch")
    elif tab == "采样与传输":
        keys = (
            "sample_count",
            "valid_generated_observation_count",
            "local_sent_message_count",
            "local_received_message_count",
            "local_application_bytes",
            "total_application_bytes",
        )
        for col, key in zip(st.columns(6), keys, strict=True):
            col.metric(key, run.metrics.get(key, "N/A"))
        decisions = result.sampling_events
        fig, ax = plt.subplots(figsize=(10, 3))
        for y, (name, label) in enumerate(
            (("sampled", "Sample"), ("sent", "Send"), ("valid_received", "Valid delivery step"))
        ):
            ax.scatter(
                decisions.loc[decisions[name], "step"] * run.config.dt_seconds / 3600,
                [y] * int(decisions[name].sum()),
                s=12,
                label=label,
                color=("#1D1D1F", "#8E8E93", "#0071E3")[y],
            )
        ax.set_yticks([0, 1, 2], ["Sample", "Send", "Valid delivery step"])
        ax.set_xlabel("Simulation time (h)")
        show_figure(fig)
        st.dataframe(decisions, hide_index=True, height=280, width="stretch")
        st.dataframe(result.communication_events, hide_index=True, height=220, width="stretch")
        st.caption(
            "每条消息为 34 字节固定应用层载荷；发送尝试计费，包含断网时失败尝试。"
            "本地预算不约束远程遥测。消息到达与有效观测接收分开记录。不是无线协议开销或能耗。"
        )
    else:
        fig, axes = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
        for ax, channel in zip(axes, CHANNELS, strict=True):
            if frame[f"std_{channel}"].notna().any():
                ax.plot(frame.time_seconds / 3600, frame[f"std_{channel}"], color="#1D1D1F")
                ax.axhline(
                    run.config.estimator.max_std[CHANNELS.index(channel)],
                    color="#86868B",
                    linestyle="--",
                )
            ax.set_ylabel(f"{channel} model SD")
        axes[-1].set_xlabel("Simulation time (h)")
        show_figure(fig)
        st.caption(
            "基线没有协方差，显示 N/A。虚线为配置的标准差降级上限；协方差未经真实数据校准。"
            "回放仅使用已经到达的观测及历史实际动作/扰动。"
        )
        st.dataframe(result.estimator_events, hide_index=True, width="stretch")
        st.dataframe(
            frame[["step", "uncertainty_fallback", *[f"control_valid_{c}" for c in CHANNELS]]],
            hide_index=True,
            height=220,
            width="stretch",
        )
    with st.expander("导出检查数据"):
        export_artifacts(run.directory, "trust_export")


def data_replay(project_root: Path, results_root: Path):
    st.subheader("CSV 数据导入与离线回放")
    st.caption(
        "实测值不等于完整物理真值。此工作区不运行控制器；缺少动作/扰动时使用明确标记的假设输入。"
    )
    default_mapping, default_replay = load_data_config(project_root / "configs/replay_example.yaml")
    draft = st.session_state.setdefault(
        "replay_draft",
        {
            "mapping": default_mapping.model_dump(mode="json"),
            "replay": default_replay.model_dump(mode="json"),
            "method": "ekf",
            "history": 24,
            "seed": 11,
        },
    )
    source_kind = st.radio(
        "数据来源", ["手写格式样例（非实测）", "上传 CSV"], horizontal=True, key="replay_source"
    )
    if source_kind == "上传 CSV":
        uploaded = st.file_uploader("本地 CSV", type="csv", key="replay_upload")
        if uploaded:
            st.session_state.replay_upload_bytes = uploaded.getvalue()
            st.session_state.replay_upload_name = uploaded.name
        raw = st.session_state.get("replay_upload_bytes")
        if raw is None:
            st.info("选择 CSV 后配置字段映射。文件只在本机处理。")
            return
    else:
        raw = (project_root / "examples/format_fixture.csv").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if draft.get("source_digest") != digest:
        dataset_id = (
            default_mapping.dataset_id
            if source_kind.startswith("手写")
            else Path(st.session_state.get("replay_upload_name", "uploaded_csv")).stem
        )
        draft["source_digest"] = digest
        draft["mapping"]["dataset_id"] = dataset_id
        st.session_state.replay_dataset = dataset_id
    try:
        columns = pd.read_csv(io.BytesIO(raw), nrows=0).columns.tolist()
    except (ValueError, pd.errors.ParserError) as exc:
        st.error(f"CSV 表头无法读取：{exc}")
        return
    mapping_data, replay_data = draft["mapping"].copy(), draft["replay"].copy()
    left, right = st.columns(2)
    mapping_data["dataset_id"] = left.text_input(
        "数据集标识", value=mapping_data["dataset_id"], key="replay_dataset"
    )
    mapping_data["origin"] = (
        "synthetic_fixture" if source_kind.startswith("手写") else "external_unverified"
    )
    timestamp_column = mapping_data["timestamp_column"]
    mapping_data["timestamp_column"] = left.selectbox(
        "时间戳列",
        columns,
        index=columns.index(timestamp_column) if timestamp_column in columns else 0,
        key="replay_timestamp",
    )
    mapped = {}
    for channel in CHANNELS:
        options = [None, *columns]
        current = mapping_data["columns"].get(channel)
        mapped[channel] = left.selectbox(
            f"{channel} 列",
            options,
            index=options.index(current) if current in options else 0,
            key=f"replay_column_{channel}",
            format_func=lambda v: "未提供" if v is None else v,
        )
    mapping_data["columns"] = mapped
    for field, label, options in (
        ("temperature_unit", "温度单位", ["C", "F", "K"]),
        ("humidity_unit", "空气湿度单位", ["percent", "fraction"]),
        ("moisture_unit", "水分单位", ["fraction", "percent"]),
        ("missing_policy", "缺测处理", ["preserve", "drop_all_missing", "error"]),
    ):
        mapping_data[field] = left.selectbox(
            label, options, index=options.index(mapping_data[field]), key=f"replay_{field}"
        )
    method = right.selectbox(
        "回放估计器",
        list(ESTIMATORS),
        index=list(ESTIMATORS).index(draft["method"]),
        key="replay_method",
    )
    history = right.number_input(
        "历史窗口（行；0 关闭）",
        min_value=0,
        max_value=10000,
        value=draft["history"],
        key="replay_history",
    )
    seed = right.number_input("随机种子", min_value=0, value=draft["seed"], key="replay_seed")
    replay_data["dropout_probability"] = right.slider(
        "人为遮蔽比例", 0.0, 1.0, float(replay_data["dropout_probability"]), key="replay_dropout"
    )
    replay_data["delay_rows"] = right.number_input(
        "到达延迟（行）", min_value=0, value=replay_data["delay_rows"], key="replay_delay"
    )
    partitions = ["calibration", "development", "final_evaluation"]
    replay_data["partition"] = right.selectbox(
        "数据用途",
        partitions,
        index=partitions.index(replay_data["partition"]),
        key="replay_partition",
    )
    with st.expander("时间范围、分段与假设输入"):
        for field, label in (
            ("start_time", "开始（含）"),
            ("end_time", "结束（不含）"),
            ("calibration_end_time", "校准结束边界"),
            ("development_end_time", "开发结束边界"),
        ):
            replay_data[field] = (
                st.text_input(label, value=replay_data[field] or "", key=f"replay_{field}") or None
            )
        mapping_data["timezone"] = st.text_input(
            "无时区时间戳的时区", value=mapping_data["timezone"], key="replay_timezone"
        )
        mapping_data["timestamp_unit"] = st.selectbox(
            "时间戳格式",
            ["datetime", "s", "ms"],
            index=["datetime", "s", "ms"].index(mapping_data["timestamp_unit"]),
            key="replay_timeunit",
        )
        expected = st.number_input(
            "预期采样间隔（秒；0 未指定）",
            min_value=0.0,
            value=mapping_data["expected_interval_seconds"] or 0.0,
            key="replay_interval",
        )
        mapping_data["expected_interval_seconds"] = expected or None
        for field in (
            "assumed_outdoor_temperature_c",
            "assumed_outdoor_humidity_pct",
            "assumed_solar_proxy",
            "assumed_evapotranspiration_proxy",
            "assumed_ventilation",
            "assumed_irrigation",
        ):
            replay_data[field] = st.number_input(
                field, value=float(replay_data[field]), key=f"replay_{field}"
            )
        st.caption(
            "无时区分段边界按 UTC。延迟/年龄/历史窗口以原始行序号计；"
            "物理预测使用实际秒差，长间隔分段积分。"
            "最终评估按开发结束边界截取，此设置不能证明参数选择过程未接触最终数据。"
        )
    draft.update(
        mapping=mapping_data, replay=replay_data, method=method, history=history, seed=seed
    )
    cfg = load_config(project_root / "configs/adaptive.yaml")
    cfg.estimator.method = method
    cfg.estimator.replay_history_steps = history if method in ("ekf", "trust_ekf") else 0
    cfg.seeds = [seed]
    fingerprint = hashlib.sha256(raw + json.dumps(draft, sort_keys=True).encode()).hexdigest()
    if st.button("预览与校验 CSV", key="preview_replay"):

        def preview():
            frame, stats = import_csv(raw, ImportConfig.model_validate(mapping_data))
            st.session_state.replay_preview = (fingerprint, frame, stats)
            return True

        run_action(preview, results_root)
    preview = st.session_state.get("replay_preview")
    if preview and preview[0] == fingerprint:
        st.dataframe(preview[1].head(30), hide_index=True, width="stretch")
        st.json(preview[2])
    if st.button("运行离线回放", type="primary", key="run_replay"):
        target = unique_target(results_root, "data_replays")
        progress = st.progress(0.0)

        def execute():
            write_replay(
                raw,
                ImportConfig.model_validate(mapping_data),
                ReplayConfig.model_validate(replay_data),
                SimulationConfig.model_validate(cfg.model_dump()),
                seed,
                target,
                completed=lambda done, total: progress.progress(done / total),
            )
            return target

        success = run_action(execute, results_root)
        if success:
            st.session_state.replay_success = (str(success), fingerprint)
    with st.expander("回放估计器对照实验"):
        comparison_seeds = st.text_input(
            "回放对照种子", value="11, 22, 33", key="measurement_seeds"
        )
        methods = st.multiselect(
            "回放对照方法", list(ESTIMATORS), default=list(ESTIMATORS), key="measurement_methods"
        )
        if st.button("运行回放对照", key="run_measurement_comparison"):
            from agritwin_cps.experiments.measurement import run_measurement_experiment

            target = unique_target(results_root, "replay_comparisons")
            progress = st.progress(0.0)

            def execute_comparison():
                data = cfg.model_dump()
                data["seeds"] = [int(v.strip()) for v in comparison_seeds.split(",")]
                run_measurement_experiment(
                    raw,
                    ImportConfig.model_validate(mapping_data),
                    ReplayConfig.model_validate(replay_data),
                    SimulationConfig.model_validate(data),
                    target,
                    methods=methods,
                    completed=lambda done, total, label: progress.progress(
                        done / total, text=label
                    ),
                )
                return target

            success = run_action(execute_comparison, results_root)
            if success:
                st.session_state.measurement_success = str(success)
        comparisons = sorted(
            (results_root / "replay_comparisons").glob("*/replay_comparison.json"), reverse=True
        )
        if comparisons:
            directory = st.selectbox(
                "恢复回放对照",
                comparisons,
                format_func=lambda p: p.parent.name,
                key="measurement_restore",
            ).parent
            st.dataframe(
                pd.read_csv(directory / "measurement_per_seed.csv"),
                hide_index=True,
                height=240,
                width="stretch",
            )
            st.dataframe(
                pd.read_csv(directory / "measurement_summary.csv"),
                hide_index=True,
                height=240,
                width="stretch",
            )
            images = sorted(directory.glob("*.png"))
            if images:
                image = st.selectbox("一致性图表", images, format_func=lambda p: p.stem)
                st.image(str(image))
            export_artifacts(directory, "measurement_export")
    saved = sorted((results_root / "data_replays").glob("*/replay.json"), reverse=True)
    if saved:
        manifest = st.selectbox(
            "恢复回放结果", saved, format_func=lambda p: p.parent.name, key="replay_restore"
        )
        success = st.session_state.get("replay_success")
        directory = (
            Path(success[0]) if success and success[0] == str(manifest.parent) else manifest.parent
        )
        if success and success[0] == str(directory) and success[1] != fingerprint:
            st.warning("草稿已变化；下方仍为上次成功回放。")
        st.image(str(directory / "replay.png"))
        st.dataframe(
            pd.read_csv(directory / "trajectory.csv"), hide_index=True, height=260, width="stretch"
        )
        st.json(json.loads((directory / "metrics.json").read_text()))
        st.caption(
            "measurement_agreement 含已同化观测，不代表独立预测精度；preupdate 为更新前一致性，"
            "heldout 仅用于零延迟的人工遮蔽分量；延迟时改用 "
            "masked_target_prediction_agreement。二者都不是物理真值误差。"
        )
        with st.expander("回放配置、来源与导出"):
            st.json(json.loads((directory / "metadata.json").read_text()))
            export_artifacts(directory, "replay_export")
    failure_details()


def adaptive_experiments(project_root: Path, results_root: Path):
    st.subheader("可信度与采样对照实验")
    st.caption("预先声明的 A–H 组；所有变体共用种子与外界随机序列。全部使用 twin_assisted 控制器。")
    use_draft = st.checkbox(
        "使用 Simulation Lab 当前已校验配置", value=False, key="adaptive_use_draft"
    )
    base = (
        st.session_state.get("lab_current_config")
        if use_draft
        else load_config(project_root / "configs/adaptive.yaml")
    )
    if base is None:
        st.info("先进入 Simulation Lab 校验配置。")
        return
    base = base.model_copy(deep=True)
    st.caption(
        f"基础配置：{base.name} · estimator={base.estimator.method}"
        f" · sampling={base.sampling.strategy}"
    )
    if use_draft and st.session_state.get("lab_draft_invalid"):
        st.warning("Simulation Lab 当前草稿无效；此处使用其最近一次已校验配置。")
    duration = st.number_input(
        "每次运行时长（小时）",
        min_value=0.1,
        value=base.steps * base.dt_seconds / 3600,
        key="adaptive_duration",
    )
    seeds = st.text_input("配对种子", value=", ".join(map(str, base.seeds)), key="adaptive_seeds")
    group = st.selectbox("实验组", ADAPTIVE_EXPERIMENTS, key="adaptive_group")
    options = list(dict.fromkeys(label for _, label, _ in variants(group, base)))
    selected = st.multiselect(
        "比较变体", options, default=options, key=f"adaptive_variants_{group}"
    )
    st.caption(
        "每个场景以首个选中且按预声明顺序排列的变体为配对参考。开发默认种子为 11/22/33，"
        "不得将调参后复跑的同一场景称为独立最终评估。"
    )
    if st.button("运行配对对照实验", type="primary", key="run_adaptive"):
        target = unique_target(results_root, "adaptive_runs")
        progress = st.progress(0.0)

        def execute():
            import math

            data = base.model_dump()
            data.update(
                steps=math.ceil(duration * 3600 / base.dt_seconds),
                seeds=[int(v.strip()) for v in seeds.split(",")],
            )
            config = SimulationConfig.model_validate(data)
            if len(selected) < 2:
                raise ValueError("选择至少两个变体进行配对比较")
            run_adaptive_experiment(
                group,
                config,
                target,
                selected_variants=selected,
                completed=lambda done, total, label: progress.progress(done / total, text=label),
            )
            return target

        success = run_action(execute, results_root)
        if success:
            st.session_state.adaptive_success = str(success)
    saved = sorted(
        (results_root / "adaptive_runs").glob("*/adaptive_experiment.json"), reverse=True
    )
    if saved:
        source = st.selectbox(
            "已完成对照实验", saved, format_func=lambda p: p.parent.name, key="adaptive_restore"
        ).parent
        st.dataframe(
            pd.read_csv(source / "per_seed.csv"), hide_index=True, height=260, width="stretch"
        )
        st.dataframe(
            pd.read_csv(source / "summary.csv"), hide_index=True, height=260, width="stretch"
        )
        figures = sorted(source.glob("*.png"))
        if figures:
            selected_figure = st.selectbox(
                "对照图表", figures, format_func=lambda p: p.stem, key="adaptive_figure"
            )
            st.image(str(selected_figure))
        st.caption(
            "Experiment Comparison 可逐指标查看全部种子、均值/样本标准差与配对差值，包括不利结果。"
        )
        with st.expander("完整导出"):
            export_artifacts(source, "adaptive_export")
    failure_details()
