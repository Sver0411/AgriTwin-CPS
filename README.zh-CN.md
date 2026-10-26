# AgriTwin-CPS 2.0

**基于仿真的温室数字孪生与信息物理系统研究平台**

本项目是独立的 Python 科研仿真软件。它实现温度、空气湿度、土壤湿度的动态模型，
虚拟传感器、独立状态估计器、通风/灌溉控制、执行器约束和可复现的故障实验。
核心实验全部支持命令行，不依赖界面、温室设备、外部数据 API 或强化学习。

核心仿真环境数据来自明确说明的简化数学模型；外部数据回放独立标记真实测量来源。参数是未校准的演示假设，不能把模拟结果
描述为真实温室实验，也不能直接用作农业操作建议。孪生方法可以更好、相当或更差。
已执行公开温度数据的离线测量一致性对照；没有完整物理模型、闭环系统或硬件验证，也没有最优性或创新性结论。

## 安装与运行

在项目根目录使用 Python 3.11 或更新版本：

```bash
uv sync --frozen --extra dev --extra ui --no-editable
source .venv/bin/activate
agritwin simulate --config configs/nominal.yaml --steps 48 --output results/my_nominal
python scripts/run_simulation.py --config configs/sensor_dropout.yaml --output results/my_fault
agritwin simulate --config configs/communication_outage.yaml --output results/my_outage
python scripts/run_experiment.py --name controller_comparison --output results/my_comparison
python scripts/run_all_experiments.py --output results/my_suite --summary-plots-only
pytest -q
ruff check .
ruff format --check .
```

`ui` 是可选依赖。也可以在虚拟环境中执行 `python -m pip install '.[dev,ui]'`。
普通安装后修改包源码，需要重新安装：
`uv sync --frozen --extra dev --extra ui --no-editable --reinstall-package agritwin-cps`。
输出目录必须为空，程序不会静默覆盖已有实验。

默认步长 300 秒，576 步共 48 小时。五个评估种子是 101、202、303、404、505。
完整实验包括 7 组、26 个场景、两种控制器，共 260 次运行。
`--estimator model_only` 可运行纯模型预测；默认是观测校正法。
这两个原有基线不是 Kalman 滤波；2.0 新增 EKF 和可信度加权 EKF。协方差未经真实数据校准。

## 已实现与验证边界

- 温室模型、天气、传感器、执行器和两种闭环控制器：已实现并通过仿真测试。
- 独立预测—校正估计器：已实现，具有时间戳检查、观测年龄和缺测计数。
- 噪声、随机/连续缺测、偏移、漂移、卡死、延迟及执行器失效：已实现。
- 本地和远程链路的延迟、丢包、断网、过期丢弃与恢复：已实现。
- 多种子配对比较、均值/样本标准差、失败记录、指标和图表：已实现。
- Streamlit 实验界面：已实现七个科研工作区、原生参数控件、多种子对比、持久化恢复、CSV/JSON/ZIP 导出和应用测试。
- 传感器启发式健康评估、EKF、有限历史回放：已实现并测试，诊断可能漏报或误报。
- 五种采样策略、采样/本地发送预算、应用层字节统计、A–H 配对实验：已实现并执行。
- CSV 导入、离线回放、真实公开数据的温度测量一致性对照：已实现并执行，范围和质量审计见文档。
- 真实设备、作物产量、实际用水/能耗、无线电性能：未验证或未建模。

`true_state` 只表示模拟器内部状态；`observed_state` 是经验证的有效观测；
`estimated_state` 是独立孪生估计。估计器和控制器不能访问模拟器真值。
远程监控断网不影响本地闭环，本地传感器链路失效则会触发年龄限制与安全回退。
安全回退规则自身也只是场景假设，并不保证所有天气下的安全。

## 2.0：可信度、自适应采样与数据回放

```bash
agritwin simulate --config configs/adaptive.yaml --output results/trust_run
agritwin adaptive --name estimators --config configs/adaptive.yaml --output results/estimator_study
agritwin adaptive --name sampling --config configs/adaptive.yaml --output results/sampling_study
agritwin adaptive --name delay_loss --config configs/adaptive.yaml --output results/delay_study
agritwin replay --csv examples/format_fixture.csv --data-config configs/replay_example.yaml \
  --config configs/adaptive.yaml --output results/format_replay
```

估计器为 `model_only`、`observation_corrected`、`ekf` 或 `trust_ekf`。
EKF 的 `replay_history_steps` 为独立历史回放开关，0 表示关闭；链路和估计器的最大数据年龄仍生效。
`health.method` 支持 basic/residual/persistent，可信度只是启发式分数。
采样策略为 fixed/change/uncertainty/trust_change/event，预算分别约束采样次数与本地观测发送字节。
默认逐步固定采样保留原基线；A/B/D/E/G 固定相同采样计划，C/F/H 明确比较调度与预算。

新增 **Sensor Trust & Sampling** 查看健康、决策、字节与协方差/回放事件；
**Data Replay** 支持上传 CSV、字段/单位配置、预览、显式运行和多估计器对照；
**Adaptive Experiments** 可选择 A–H 组、变体、种子和时长，读取 Simulation Lab 的故障/预算配置。
修改参数不会自动启动实验。成功结果可恢复，失败诊断和上次成功结果分别保留。

已读取用户下载的南非温室公开数据，按时间质量预先保留开发片段 1,717 行、独立回放片段 859 行。
原文件有重复/跳变等时间问题，未自动修正日期。处理、许可、哈希、排除规则和复现步骤见
[数据回放与来源](docs/DATA_REPLAY.md)。原始数据不会提交到 Git。

**负面结果也保留**：该公开片段中，默认可信度加权 EKF 明显差于原观测校正法和普通 EKF。
不能把测量一致性当成潜在真实状态的精度，也不能将本地发送减少等同于实际能耗降低。
新功能的公式、参数单位和边界见 [传感器与估计](docs/SENSOR_TRUST_ESTIMATION.md)、
[采样与资源](docs/ADAPTIVE_SAMPLING.md) 和 [实际结果](docs/RESULTS.md)。

## 结果与文档

每次运行保存配置、随机种子、包源码哈希、环境元数据、轨迹、通信/观测/执行事件、
恢复事件、指标与图表。实验另外保存逐种子指标、均值/标准差及“孪生减基线”的配对差值。
空指标表示未测量或不适用；未在观察窗口内恢复的事件单独标记为右删失，不能当作立即恢复。
图表与数值全部来自实际执行的仿真。

## 科研实验界面

启动：`streamlit run app.py`。采用白底、黑色标题、浅灰分区，仅在科研图表中保留少量蓝色与不同线型。

- **Overview**：实际运行状态与关键指标、三类状态说明、系统数据流图；无结果时显示 N/A。
- **Simulation Lab**：六个现有场景预设，时长、步长、种子、控制器、估计器、噪声/缺测和故障设置；完整 YAML 收纳于 Advanced Settings。
- **State & Fault Analysis**：共享时间窗口下的状态曲线、估计误差、故障证据、请求动作与实际动作。
- **Experiment Comparison**：读取真实界面/CLI 实验，展示每个种子、均值与样本标准差、配对差值、恢复删失计数与数据导出。

只有点击 **Run Simulation** 才执行实验。修改参数会提示结果仍属于上次成功配置；运行失败保留旧结果并提供诊断。
界面直接调用原运行器，结果保存在 `results/ui_runs/`，包含完整配置、指标、事件、源码哈希与环境元数据。
刷新可恢复最近成功实验，侧边栏可选择历史结果；草稿跨工作区保留，浏览器刷新后草稿重新初始化。
未完成的运行没有成功标记，不会被恢复为成功结果。`AGRITWIN_RESULTS_DIR` 可设置其他本地结果根目录。

配置故障、实际记录、校验拒绝、启发式健康诊断与观察到的恢复分别标注。疑似/持续异常不证明故障原因；
模型失配也可能触发告警。回退依据输入有效性、年龄与 EKF 标准差限制，不依据动作形状猜测。
缺测不补零、不连线；误差使用独立单位坐标轴。单个有效种子的标准差未定义，不显示为零，也不生成未经计算的置信区间。
可导出 CSV/JSON 或准备完整 ZIP；界面不会上传数据。CLI 复现方式保持不变。
生成结果保留在本地 `results/`，默认不提交到 Git。
详细英文技术说明、公式、单位、研究协议和局限性见 [英文 README](README.md) 与 [docs](docs/ARCHITECTURE.md)。
