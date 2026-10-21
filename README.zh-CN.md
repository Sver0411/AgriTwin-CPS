# AgriTwin-CPS

**基于仿真的温室数字孪生与信息物理系统研究平台**

本项目是独立的 Python 科研仿真软件。它实现温度、空气湿度、土壤湿度的动态模型，
虚拟传感器、独立状态估计器、通风/灌溉控制、执行器约束和可复现的故障实验。
核心实验全部支持命令行，不依赖界面、温室设备、外部数据 API 或强化学习。

所有环境数据来自明确说明的简化数学模型。参数是未校准的演示假设，不能把模拟结果
描述为真实温室实验，也不能直接用作农业操作建议。孪生方法可以更好、相当或更差。
目前没有公开数据验证或物理硬件验证，也没有最优性或创新性结论。

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
两种方法都不是 Kalman 滤波，也没有输出未经计算的置信区间。

## 已实现与验证边界

- 温室模型、天气、传感器、执行器和两种闭环控制器：已实现并通过仿真测试。
- 独立预测—校正估计器：已实现，具有时间戳检查、观测年龄和缺测计数。
- 噪声、随机/连续缺测、偏移、漂移、卡死、延迟及执行器失效：已实现。
- 本地和远程链路的延迟、丢包、断网、过期丢弃与恢复：已实现。
- 多种子配对比较、均值/样本标准差、失败记录、指标和图表：已实现。
- Streamlit 实验界面：已实现四个科研工作区、原生参数控件、多种子对比、持久化恢复、CSV/JSON/ZIP 导出和应用测试。
- 真实设备、公开数据、作物产量、实际用水/能耗、无线电性能：未验证或未建模。

`true_state` 只表示模拟器内部状态；`observed_state` 是经验证的有效观测；
`estimated_state` 是独立孪生估计。估计器和控制器不能访问模拟器真值。
远程监控断网不影响本地闭环，本地传感器链路失效则会触发年龄限制与安全回退。
安全回退规则自身也只是场景假设，并不保证所有天气下的安全。

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

配置故障、实际记录、校验拒绝、推导的回退条件与观察到的恢复分别标注。没有自动漂移/卡死检测器；
重叠的随机缺测与注入缺测不能仅凭 NaN 区分。回退依据记录的输入有效性与年龄推导，不依据动作形状猜测。
缺测不补零、不连线；误差使用独立单位坐标轴。单个有效种子的标准差未定义，不显示为零，也不生成未经计算的置信区间。
可导出 CSV/JSON 或准备完整 ZIP；界面不会上传数据。CLI 复现方式保持不变。
生成结果保留在本地 `results/`，默认不提交到 Git。
详细英文技术说明、公式、单位、研究协议和局限性见 [英文 README](README.md) 与 [docs](docs/ARCHITECTURE.md)。
