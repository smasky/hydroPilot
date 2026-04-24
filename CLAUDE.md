# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 沟通约定

- 与用户沟通时，称呼用户为“小天”。
- 讨论类文档使用中文。
- 代码注释使用英文。
- `.history/` 下的文件一律忽略。
- 与 Claude 相关的项目文件放在 `.claude/` 下。
- 项目技术文档与长期记忆放在 `.claude/memory/` 下。
- 对于用户已经明确点名的目标文件，可以直接修改；如果涉及跨目录的大重构、批量重命名、公共 API 迁移，先与用户确认范围再动手。

## 项目定位

hydroPilot 是一个**配置驱动**的水文模型实验编排框架，用于把外部模型运行、参数写入、结果提取、指标计算、目标/约束评估和结果记录，统一组织成一条可重复执行的流水线。

当前项目的核心定位是：

- **general mode** 是真正的模型无关核心；
- **template mode** 是对特定模型的配置展开层；
- 当前仓库里唯一真正注册的内置模板是 **SWAT**；
- APEX / HBV / VIC / HEC-HMS 等更适合表述为“计划支持”，不要写成“已经内置完成”。

## 当前源码结构（按真实目录，而不是旧设计稿）

```text
src/hydro_pilot/
  api/             # 对外入口，当前 SimModel 在这里
  cli/             # 命令行入口，如 validate
  config/          # 配置加载、路径解析、schema、RunConfig
  engine/          # 运行期聚合逻辑（adapter / params / series / evaluation）
  io/              # readers / writers / runners
  models/          # 模板注册与模型知识，当前主要是 swat/
  reporting/       # SQLite / CSV / error 日志持久化
  validation/      # 面向用户的配置诊断入口
  integrations/    # 外部优化框架集成，当前是 UQPyL
  errors.py        # RunError 定义
```

补充说明：

- `.claude/memory/project_design_decisions.md` 记录了当前最重要的非显然设计决策。
- `.claude/memory/project_swat_reference.md` 记录了 SWAT 测试工程、文件格式和模板背景信息。
- `.claude/memory/recommended_source_structure.md` 是**推荐演进蓝图**，不是当前已经完全落地的实际结构。

## 一条先看懂的运行链路

当前主流程可以概括为：

`prepare_config / load_config`
→ `RunConfig`
→ `SimModel`
→ `ModelAdapter`
→ `ParamManager`
→ `SubprocessRunner`
→ `SeriesExtractor`
→ `Evaluator`
→ `RunReporter`

更具体地说：

1. `config.loader.prepare_config()` 负责读取 YAML、识别 `version`、在 template mode 下展开为 general raw dict，并做 general validation。
2. `config.loader.load_config()` 把展开后的 raw dict 解析成 `RunConfig`。
3. `api/sim_model.py` 中的 `SimModel` 负责创建运行目录、复制 `instance_*` 工作副本、调度批量评估、汇总错误和 reporter 生命周期。
4. `engine/adapter/adapter.py` 中的 `ModelAdapter` 聚合四块能力：
   - 参数变换/写入
   - 模型执行
   - 结果提取
   - 评估计算
5. `reporting/reporter.py` 异步消费运行记录，输出 `results.db`、`summary.csv`、`error.jsonl`、`error.log` 以及可选的系列 CSV。

## 配置系统的真实规则

### 1. 两种配置入口

- `version: general`
  - 直接使用标准 schema。
- `version: swat`
  - 先做 SWAT 专用校验与展开，再转成 general 配置。

### 2. template 展开后的 general YAML 输出位置

当前实现中，template 展开后的 `<原文件名>_general.yaml` 会被写到**源 YAML 同目录**，不是 `workPath`。

如果后续修改行为，必须同步更新：

- `config/loader.py` 的注释/文档；
- README 中的说明；
- 相关测试与示例。

### 3. 参数链路

当前参数层是两段式：

- **design parameters**：优化器直接操作的 `X`
- **physical parameters**：最终写入模型输入文件的 `P`

主链路为：

`X -> Transformer -> physical vector P -> ParamManager -> writer tasks -> target files`

关键实现点：

- `ParametersSpec.transformer` 可选；未设置时，默认 `P == X`。
- `P` 会自动注入运行上下文，不需要手工 cache。
- writer 的组织粒度是**文件级任务**，不是“整个模型一个 writer”。
- `ParamManager` 会先按 `(target_file, writer_type)` 注册写入任务，再在运行时把值分发给对应 writer。
- 当前内置 writer 只有 `fixed_width`。

### 4. series / derived / evaluation 规则

当前评估上下文已经不再使用旧的 `expr` + `cache` 思路，而是：

- `series.sim`：可以是 reader，也可以是 `call`
- `series.obs`：只能是 reader
- `derived`：统一通过 `call`
- `functions`：分为 `builtin` 与 `external`

上下文 key 使用点号命名：

- `flow.sim`
- `flow.obs`
- `tn.sim`

不要重新引入旧的下划线上下文命名，也不要重新引入 `expr`。

### 5. FunctionManager

`engine/evaluation/func_manager.py` 负责：

- 注册 builtin functions
- 从外部 Python 文件加载 external functions
- 校验 external function 的声明参数是否与函数签名兼容

当前内置函数包括：

- `NSE`
- `KGE`
- `R2`
- `RMSE`
- `MSE`
- `PBIAS`
- `LogNSE`
- `sum_series`

## 错误、warning 与 on_error 语义

这是当前项目里最容易被改坏的一块，修改 evaluator / reporter / sim_model 时必须先理解清楚。

### 1. RunError 不是只有 fatal

`errors.py` 中的 `RunError` 带有：

- `severity = "fatal"`
- `severity = "warning"`

warning 会进入 `context["warnings"]`，而不是通过抛异常中断整次运行。

### 2. derived 的 fatal / warning 规则

`Evaluator` 会在初始化阶段构建 `fatalDerivedIds`：

- 如果某个 derived 被 objective 或 constraint 直接/间接依赖，那么它失败属于 **fatal**。
- 如果某个 derived 只被 diagnostic 使用，那么它失败属于 **warning**，并回填 `NaN`。

不要随意改这条规则，否则会直接改变优化问题的失败语义。

### 3. on_error 默认值

默认回填规则是：

- objective: `min -> +inf`, `max -> -inf`
- constraint: `+inf`
- diagnostic: `NaN`

### 4. clamp warning

writer 在写物理参数时如果发生硬边界截断，会按参数名聚合 warning，而不是每个文件报一条。

## Reporter 设计要点

`RunReporter` 当前是异步后台线程模型。

主要输出：

- `backup/results.db`
- `backup/summary.csv`
- `backup/error.jsonl`
- `backup/error.log`
- 可选的 series CSV

关键点：

- reporter 与模型执行解耦；
- CSV / DB 的 summary 字段顺序保持一致；
- error 与 warning 都会被落盘，只是 severity 不同；
- holding pen 允许慢任务稍后写出，因此 CSV 顺序不一定严格按提交顺序；
- reporter 一旦崩溃，会通过 `_crash_event` 让主线程感知。

## SWAT 模板层目前的职责

`models/swat/` 当前是仓库里最完整的一组模型知识模块，职责包括：

- `template.py`
  - 模板入口，把 `version: swat` 的简化配置转换成 general raw dict
- `validate.py`
  - SWAT 特定的前置校验
- `discovery.py`
  - 读取 `file.cio` / `fig.fig` / `.sub` / `.hru`，抽取项目元数据
- `builder.py`
  - 设计参数、物理参数、filter、location 展开
- `series.py`
  - SWAT 输出变量与行列位置解析
- `library.py` / `swat_db.yaml` / `series_db.yaml`
  - 参数与序列元数据库

记住：SWAT 模板层的职责是“把 SWAT 知识折叠进配置展开”，而不是把通用运行逻辑写回主流程。

## 当前最常用的命令

### 安装

```bash
pip install -e .
```

### 安装开发依赖

```bash
pip install -e .[dev]
```

### 安装 UQPyL 集成依赖

```bash
pip install -e .[uqpyl]
```

### 运行全部测试

```bash
pytest
```

### 运行配置校验相关测试

```bash
pytest tests/test_validate.py
```

### 运行 SWAT 月尺度 IO 协议测试

```bash
pytest tests/test_monthly_complex_io_protocol.py
```

### 运行配置校验 CLI

```bash
hydropilot-validate path/to/config.yaml
```

## 修改代码时的优先原则

### 1. 优先保持分层，而不是继续把逻辑塞回 SimModel

`SimModel` 现在已经同时承担了：

- 配置加载
- workspace 生命周期
- instance 副本管理
- 并行调度
- reporter 生命周期
- 终止信号清理

因此：

- 新的模型知识不要继续塞进 `SimModel`
- 新的 reader / writer / runner 能力优先下沉到 registry 与 io 层
- 新的模板行为优先放在 `models/<model>/` 下

### 2. 修改 schema 时，要联动三处

任何配置字段变化，至少联动：

- `config/schema/*`
- `validation/*`
- `examples/` 与 `tests/fixtures/configs/`

如果是 template mode 相关字段，还要联动：

- `models/<template>/validate.py`
- `models/<template>/template.py`
- 对应 builder / series / discovery 模块

### 3. 修改 public API 时，不要只改一半

当前仓库正处在一次结构迁移的中间态。凡是涉及 public import path、README 示例、integration 入口的修改，都必须成组处理。

## 当前仓库里已经能看到的结构性坑点

这些不是抽象建议，而是当前代码里已经存在的真实风险点。改动相关模块时要优先注意。

### 1. public import surface 有路径漂移

当前代码里至少有这些不一致：

- `src/hydro_pilot/api/sim_model.py` 里使用了 `from ..adapter import ModelAdapter`，但实际 adapter 在 `engine/adapter/`
- `src/hydro_pilot/integrations/__init__.py` 引用了不存在的 `uqpyl_adapter`
- `src/hydro_pilot/integrations/uqpyl.py` 使用了 `from ..sim_model import SimModel`，但当前 `SimModel` 在 `api/sim_model.py`
- README 里仍然写着旧导入路径：
  - `from hydro_pilot.sim_model import SimModel`
  - `from hydro_pilot.wrappers import UQPyLAdapter`

如果要修这块，必须把：

- 代码导入路径
- `__init__.py` re-export
- README 示例
- 可能的测试覆盖

一起修，不要只修单个文件。

### 2. validation 是分层的，但还有命名过渡痕迹

当前存在：

- `src/hydro_pilot/validation/`
- `src/hydro_pilot/config/validation/`（目前基本是空壳）

如果继续重构校验层，要先决定：

- 是把“用户可见诊断入口”稳定放在 `validation/`
- 还是把它逐步并回 `config/validation/`

在没有迁移计划前，不要继续复制出第三套 validation 命名空间。

### 3. SWAT 项目发现与 schema 校验耦合得比较紧

当前 `validate_swat_config()` 会先检查 `file.cio` / `fig.fig` 是否存在，再进入 SWAT series shortcut 校验。

这意味着：

- 本地没有真实 SWAT 工程时，很多更靠后的配置错误会被更早的路径错误掩盖；
- CI / 跨平台环境里，Windows 风格路径很容易直接触发 projectPath 失败；
- 某些测试会因为 discovery 前置而拿不到更精确的字段级诊断。

如果后续重构 validation，优先考虑分成：

- schema / syntax 级校验
- template semantic 校验
- project discovery 校验

而不是全部揉在一个入口里。

### 4. 路径处理需要特别注意跨平台行为

当前 `resolve_config_path()` 直接使用 `Path(path)` 判断绝对路径。在非 Windows 环境里，像 `E:\DJBasin\TxtInOutFSB` 这样的字符串不会被识别成绝对路径，最终会被错误拼到 YAML 所在目录下。

这会影响：

- SWAT 测试配置
- 示例配置
- template validation
- 任何需要兼容 Windows 样例路径的 CI 场景

### 5. 当前风格是“历史 camelCase + Python snake_case 混用”

不要在一次普通功能提交里顺手做全局命名风格清洗。当前仓库已有很多历史字段与方法名直接对齐 YAML：

- `projectPath`
- `workPath`
- `readerType`
- `writerType`
- `flushInterval`
- `holdingPenLimit`

因此更安全的做法是：

- 修改已有模块时，优先保持附近代码风格一致；
- 只有在用户明确要求时，才做大规模命名规范化。

## 推荐的工作方式

### 当你要新增一个模型模板时

优先新增：

- `models/<model>/template.py`
- `models/<model>/validate.py`
- `models/<model>/builder.py`
- `models/<model>/series.py`
- 对应的 library / yaml db

不要先去改 `SimModel` 主链路。

### 当你要新增一个文件格式 reader / writer 时

优先新增：

- `io/readers/<type>.py` 或 `io/writers/<type>.py`
- 对应 registry 注册
- validation 覆盖
- 最小 example / test

不要在现有 reader / writer 里塞满 `if file_type == ...` 分支。

### 当你要改 evaluation 语义时

必须先检查：

- `Evaluator.fatalDerivedIds`
- `on_error` 默认值
- reporter 如何记录 warning / fatal
- 示例配置与测试是否仍表达相同语义

## 建议优先阅读的文件

当需要快速进入项目时，按这个顺序看：

1. `src/hydro_pilot/api/sim_model.py`
2. `src/hydro_pilot/config/loader.py`
3. `src/hydro_pilot/config/schema/run_config.py`
4. `src/hydro_pilot/engine/adapter/adapter.py`
5. `src/hydro_pilot/engine/params/manager.py`
6. `src/hydro_pilot/engine/series/extractor.py`
7. `src/hydro_pilot/engine/evaluation/evaluator.py`
8. `src/hydro_pilot/reporting/reporter.py`
9. `src/hydro_pilot/models/swat/template.py`
10. `.claude/memory/project_design_decisions.md`

## 当前判断项目状态时的一句话总结

这个仓库已经从“围绕单一模型脚本化拼装”的阶段，走到了“以 general schema 为核心、以 template 封装模型知识、以 reporter 保证运行记录、以 validation 提供用户反馈”的框架阶段；但它仍处于一次结构整理的中间态，尤其是 **public import surface、validation 分层、路径跨平台处理** 这三块，后续改动时要格外谨慎。
