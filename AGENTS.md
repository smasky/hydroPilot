# AGENTS.md

This file provides guidance to Claude Code when working in this repository.

## 沟通约定

- 与用户讨论架构、方案、文档时，默认使用中文。
- 代码注释与标识符风格，默认遵循当前代码文件已有风格。
- 新增代码默认使用驼峰风格命名；只有在需要兼容第三方接口、Python 特定约定或历史 YAML 字段时例外。
- 不要引用已经删除的旧目录结构，例如 `core/`、`engine/adapter/`、`engine/params/`、`engine/series/`。
- 与 Claude 相关的草稿、计划、记忆文件，如果将来需要新增，统一放在 `.claude/` 下；但要先确认是否真的需要保留，避免再次堆积历史文档。
- 目前不需要向后兼容，正在开发阶段。

## 项目定位

HydroPilot 是一个配置优先的水文模型实验编排框架。它把以下能力组织成一条可重复执行的流水线：

- 参数空间定义与变换
- 参数写入模型输入文件
- 外部模型执行
- 模拟结果序列提取
- 指标 / 目标 / 约束 / 诊断计算
- 运行记录与结果持久化

当前需要坚持的定位：

- `general` 是真正的模型无关核心模式
- `template` 是模型特定的配置展开层
- 当前唯一内置且已注册的模板是 `swat`
- APEX / HBV / VIC / HEC-HMS 仍应视为规划中，而不是“已内置支持”

## 当前目录结构

当前真实源码结构如下：

```text
src/hydropilot/
  api/           # 对外 API，当前主要是 SimModel
  cli/           # 命令行入口，当前已有 hydropilot-validate
  config/        # 配置加载、路径解析、schema、RunConfig
  evaluation/    # FunctionManager 与标量评估
  integrations/  # 外部优化框架适配，当前是 UQPyL
  io/            # readers / writers / runners
  models/        # 模板注册与模型特定知识，当前主要是 swat/
  params/        # 参数空间、写入计划、写入应用
  reporting/     # results.db / summary.csv / error 日志
  runtime/       # Session / Workspace / Executor / Context
  series/        # SeriesPlan / ObsStore / SeriesExtractor
  validation/    # 面向用户的配置诊断入口
```

不要再把现在的结构描述成旧的：

- `core/`
- `engine/evaluation`
- `engine/params`
- `engine/series`
- `ModelAdapter`
- `ParamManager`

这些都已经不是当前主结构。

## 一眼看懂的两条主链路

### 1. 配置链路

当前配置入口在 `src/hydropilot/config/loader.py`：

```text
YAML
  -> prepare_config()
  -> template expansion (if version != general)
  -> general validation
  -> RunConfig
```

关键事实：

- `version: general` 直接进入 general 校验与 `RunConfig`
- `version: swat` 先做 SWAT 校验与展开，再转成 general raw dict
- 模板展开后的 `<name>_general.yaml` 目前写在源 YAML 同目录，不是 `workPath`

### 2. 运行时链路

当前运行入口在 `src/hydropilot/api/sim_model.py`：

```text
SimModel
  -> Session
  -> Workspace
  -> Executor
     -> ExecutionServices
        -> FunctionManager
        -> ParamSpace
        -> ParamWritePlan
        -> ParamApplier
        -> SeriesPlan
        -> ObsStore
        -> SubprocessRunner
        -> SeriesExtractor
        -> Evaluator
  -> RunReporter
```

职责拆分要点：

- `Session` 管生命周期：workspace、reporter、close、退出清理
- `Workspace` 管运行目录与 instance 副本
- `Executor` 管批量 evaluate 调度与单次 run 流程
- `ExecutionServices` 负责装配各能力对象
- `RunReporter` 异步落盘结果

## 参数链路

当前参数层已经拆成了稳定的几块：

- `ParamSpace`：面向优化器的设计变量信息
- `ParamWritePlan`：把 physical 参数整理成按文件 / writer 归并的写入任务
- `ParamApplier`：把一次 `X` 应用到运行目录中的目标文件
- `transformer`：可选，把 design space 映射到 physical space

应按下面的理解来维护：

```text
X
  -> transformer (optional)
  -> P
  -> ParamWritePlan
  -> writer tasks
  -> model input files
```

关键事实：

- `design parameters` 是优化器看到的输入
- `physical parameters` 是最终写入文件的参数
- 当前内置 writer 只有 `fixed_width`
- `writerType` 是稳定 schema，不要再移除
- `P` 会写入运行上下文，供 reporter 使用

## 序列链路

当前序列层已经拆成独立包：

- `SeriesPlan`：整理 series 定义
- `ObsStore`：缓存 obs 数据
- `SeriesExtractor`：提取 sim / obs，并处理 `series.sim.call`

关键规则：

- `series.sim` 可以是 reader，也可以是 `call`
- `series.obs` 只能是 reader
- `derived` 统一通过 `call`
- 上下文 key 使用点号命名，例如：
  - `flow.sim`
  - `flow.obs`
  - `tn.sim`

不要重新引回旧的 `expr` 思路，也不要改回旧的下划线命名上下文。

## validation 的现状

当前用户可见的校验入口在：

- `src/hydropilot/validation/general.py`
- `src/hydropilot/models/swat/validate.py`

当前原则：

- general schema 校验放在 `validation/`
- reader / writer 的具体字段校验仍由各自实现负责
- `readerType` / `writerType` 缺失时，要尽早给出诊断
- schema 改动时，至少同步：
  - `config/schema/*`
  - `validation/*`
  - `examples/`
  - `tests/`

不要再新开一套第三套 validation 命名空间。

## 路径语义

这是当前项目里非常重要、也很容易改坏的一点：

- `obs.file` 按配置文件目录解析
- `sim.file` 按运行时工作目录 / project 副本解析

也就是说，像 `output.rch` 这样的模拟输出，在配置里通常应写成运行时相对路径，而不是 YAML 相对路径。

另外，`resolve_config_path()` 当前仍然直接依赖 `Path(path).is_absolute()`。这对非 Windows 环境下解析 `E:\\...` 这种路径并不稳妥。涉及跨平台路径行为时要特别谨慎。

## error / warning / on_error 语义

这部分不要轻易改。

### RunError

当前 `src/hydropilot/runtime/errors.py` 中的 `RunError` 支持：

- `severity = "fatal"`
- `severity = "warning"`

warning 会进入 `context["warnings"]`，不会直接中断整次运行。

### on_error 默认值

当前错误回填语义是：

- objective: `min -> +inf`, `max -> -inf`
- constraint: `+inf`
- diagnostic: `NaN`

### derived 的 fatal / warning 区分

如果某个 derived 被 objective / constraint 依赖，那么失败应被视为 fatal；如果只用于 diagnostic，则更适合 warning + `NaN` 回填。

改 evaluator 时，必须先确认这套语义没有被破坏。

## Reporter 现状

`RunReporter` 当前是异步后台线程模型，主要输出：

- `archive/results.db`
- `archive/summary.csv`
- `archive/error.jsonl`
- `archive/error.log`
- 可选的 series CSV

维护时要记住：

- reporter 与执行流程解耦
- warning 和 fatal 都会落盘，只是 severity 不同
- 持久化字段顺序要保持稳定
- reporter 崩溃后，主流程会感知到 submit 失败

## SWAT 模板层职责

`src/hydropilot/models/swat/` 当前负责的是“把 SWAT 知识折叠进模板展开”，而不是承担通用运行时职责。

各模块大致职责：

- `template.py`：`version: swat` -> general raw dict
- `validate.py`：SWAT 特定的前置校验
- `discovery.py`：读取 SWAT 工程元数据
- `builder.py`：参数展开与 physical 参数构建
- `series.py`：SWAT 输出变量到 general series 的映射
- `library.py` / `swat_db.yaml` / `series_db.yaml`：SWAT 参数与序列知识库

如果以后增加新模板，优先在 `models/<model>/` 下扩展，而不是回头把模型知识塞进 runtime。

## 当前公开入口

当前公开 API / CLI 以这几个为准：

- Python API:
  - `from hydropilot import SimModel`
  - `from hydropilot.integrations import UQPyLAdapter`
- CLI:
  - `hydropilot-validate`

不要再使用旧 README 里那种路径：

- `from hydropilot.sim_model import SimModel`
- `from hydropilot.wrappers import UQPyLAdapter`

## 常用命令

安装：

```bash
pip install -e .
```

安装开发依赖：

```bash
pip install -e .[dev]
```

安装 UQPyL 集成依赖：

```bash
pip install -e .[uqpyl]
```

运行全部测试：

```bash
pytest
```

运行配置校验测试：

```bash
pytest tests/test_validate.py
```

运行行为锁测试：

```bash
pytest tests/test_runtime_behavior_locks.py
```

运行月尺度 SWAT IO 协议测试：

```bash
pytest tests/test_monthly_complex_io_protocol.py
```

运行配置校验 CLI：

```bash
hydropilot-validate path/to/config.yaml
```

## 修改代码时的优先原则

### 1. 优先维护现有分层

新逻辑优先放到正确层里：

- 模板知识 -> `models/`
- reader / writer / runner -> `io/`
- 参数写入组织 -> `params/`
- 序列抽取 -> `series/`
- 生命周期与调度 -> `runtime/`

不要再把逻辑回灌进一个“大而全”的入口对象。

### 2. schema 改动必须联动

只要 YAML 字段变化，至少检查：

- `config/schema/*`
- `validation/*`
- `models/swat/*`（如果模板相关）
- `examples/`
- `tests/fixtures/`
- README / 使用示例

### 3. public API 改动必须成组处理

如果改了 import path、对外入口、README 示例、integration 入口，必须一起改，不要只修一个点。

### 4. 不要顺手做全局命名清洗

当前仓库仍然是 YAML 历史字段与 Python 命名混用，例如：

- `projectPath`
- `workPath`
- `readerType`
- `writerType`
- `flushInterval`
- `holdingPenLimit`

除非是明确的专项重构，否则不要在普通功能提交里顺手全仓统一命名风格。

## 推荐阅读顺序

要快速理解项目，建议按这个顺序看：

1. `src/hydropilot/api/sim_model.py`
2. `src/hydropilot/config/loader.py`
3. `src/hydropilot/config/schema/run_config.py`
4. `src/hydropilot/runtime/session.py`
5. `src/hydropilot/runtime/executor.py`
6. `src/hydropilot/runtime/services.py`
7. `src/hydropilot/params/write_plan.py`
8. `src/hydropilot/series/extractor.py`
9. `src/hydropilot/evaluation/evaluator.py`
10. `src/hydropilot/reporting/reporter.py`
11. `src/hydropilot/models/swat/template.py`

## 一句话总结当前项目状态

这个仓库已经从“围绕单模型脚本堆叠”的阶段，进入了“以 general schema 为核心、以 template 承载模型知识、以 runtime 编排执行、以 reporter 记录结果、以 validation 提供反馈”的框架阶段。

接下来最重要的，不是再发明新的中间层，而是持续让：

- 结构更稳定
- 入口更清晰
- 路径与校验语义更一致
- 对外文档和真实代码保持同步
