# 架构设计

本文档描述的是 HydroPilot 当前代码库里已经存在的架构。
重点是解释 `src/hydro_pilot` 中真实的执行路径，方便阅读、调试和后续扩展。

## 总览

HydroPilot 可以拆成两条主要链路：

```text
配置链路
  YAML 配置
    -> 校验与模板展开
    -> RunConfig
```

```text
运行链路
  SimModel
    -> Session
    -> Workspace
    -> Executor
    -> ExecutionServices
    -> RunReporter
```

这两条链路相关，但并不相同。

- 配置链路负责把用户 YAML 转成一个经过校验的 `RunConfig`
- 运行链路负责使用这个 `RunConfig` 执行模型、提取输出、计算指标并落盘结果
- CLI 校验命令只会走配置链路
- `SimModel` 会同时用到配置链路和运行链路

## 主要模块

当前运行时相关的主要模块如下：

```text
src/hydro_pilot/
  api/           对外公开入口，例如 SimModel
  cli/           命令行接口
  config/        配置加载、路径解析、schema 转换
  evaluation/    派生量、目标函数、约束、诊断项计算
  io/            模型 runner、文件 reader、文件 writer
  models/        模板注册表和模型专属模板逻辑
  params/        参数空间与参数写入
  reporting/     运行结果持久化与输出产物
  runtime/       session、workspace、executor、运行时上下文
  series/        模拟值/观测值提取规划
  validation/    面向用户的配置诊断
```

## 配置链路

配置链路从 YAML 文件开始，到 `RunConfig` 结束。

```text
YAML
  -> prepare_config()
  -> 可选的模板展开
  -> general 校验
  -> RunConfig.from_raw()
  -> load_config()
```

### 1. 原始 YAML 加载

`config.loader.prepare_config()` 是配置准备阶段的共享核心入口。

它负责：

- 解析配置文件路径
- 把 YAML 读成 Python mapping
- 读取 `version`
- 当 `version != general` 时执行模板展开
- 对展开后的配置做校验
- 构建最终的 `RunConfig`

如果这些步骤中的任意一步失败，它会抛出 `ConfigPreparationError`，并携带已经翻译好的 diagnostics。

### 2. 模板展开

HydroPilot 同时支持 general 模式和模板模式。

- `version: general` 表示 YAML 已经直接描述了运行时配置
- 像 `version: swat` 这样的版本会通过 `models.registry` 中的模板注册表进行解析

调用路径如下：

```text
version != general
  -> get_template(version)
  -> template.build_config(raw, base_path)
  -> expanded general config
```

这里有几个关键点：

- 模板专属校验可以在展开前执行
- 运行时始终针对“展开后的 general 配置”工作
- 当 `load_config()` 成功时，HydroPilot 会在源 YAML 同目录写出一个 `<source_stem>_general.yaml` 供用户查看；模板配置会被展开，general 配置会写出补全默认值后的版本

最后这一点只发生在 `load_config()` 路径中，不会发生在 CLI 校验路径中。

### 3. 校验

HydroPilot 当前有两层校验。

`validation.entry.validate_config()` 是面向用户的校验入口。它会调用 `prepare_config()`，再把异常转换为适合 CLI 展示的 diagnostics 列表。

`validation.general.validate_general_config()` 是 general 配置的结构化与语义校验器。它会检查这些内容：

- `basic` 中的必需字段
- 参数定义
- writer 规格
- series 提取规格
- 外部 function 文件是否存在

另外还有模板专属校验，例如 SWAT 配置会在模板展开前先做一轮校验。

### 4. 直接运行时的配置加载

公开的 Python API 不会调用 CLI 校验器，而是直接调用 `load_config()`。

```text
SimModel(...)
  -> load_config(...)
  -> prepare_config(...)
  -> RunConfig
```

这意味着：

- 底层的配置准备和校验逻辑是复用的
- CLI 专属行为不会被复用
- 直接运行时遇到配置错误会抛异常，而不是像 CLI 一样打印 diagnostics 并返回退出码

## CLI 校验链路

当前的 CLI 命令只是对校验入口做了一层很薄的包装。

```text
hydropilot-validate
  -> hydro_pilot.cli.validate.main()
  -> validate_config()
  -> prepare_config()
```

它只负责：

- 解析配置文件路径参数
- 执行校验
- 打印 diagnostics
- 当存在错误时返回退出码 `1`，否则返回 `0`

CLI 不会创建 `Session`、`Workspace` 或 `Executor`。它只负责做配置校验。

## 运行链路

公开的运行入口从 `SimModel` 开始。

```text
SimModel
  -> Session
  -> Workspace
  -> Executor
     -> ExecutionServices
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

### 1. SimModel

`api.sim_model.SimModel` 是当前主要的对外 API 对象。

它负责：

- 加载配置
- 创建 `Session`
- 暴露输入维度、边界、输出数量等运行时元信息
- 把实际计算委托给 `Session.evaluate()`

`SimModel` 本身只是一个轻量 API 外观层，不负责真正的调度逻辑。

### 2. Session

`runtime.session.Session` 持有一份已加载配置对应的完整运行时生命周期。

它会创建：

- `Workspace`
- `Executor`
- `RunReporter`

它还负责：

- 把 reporter 注入 executor
- 对外提供 `evaluate()`
- 在正常关闭、进程退出和部分信号场景下执行清理

因此，`Session` 是“一次运行环境”的生命周期边界。
默认情况下，`Session.close()` 会清理 `instance_*` 目录，只保留运行目录下的 `archive/`。
如果需要保留运行现场用于调试，可以设置 `basic.keepInstances: true`。

### 3. Workspace

`runtime.workspace.Workspace` 会在如下目录下创建一个独立运行目录：

```text
<workPath>/tempRun/<timestamp>/
```

在这个运行目录中，它会：

- 为每个并行 worker 创建一个 `instance_<n>` 目录
- 把配置中的 `projectPath` 复制到每个 instance 目录中
- 创建 `archive/` 目录
- 把原始配置复制到 `archive/`
- 当 `_general.yaml` 存在时，把它也复制到 `archive/`
- 当配置中存在 observation 文件时，把这些观测文件复制到 `archive/`

默认情况下，`instance_*` 目录是临时目录，会在生命周期结束时清理。
只有启用 `basic.keepInstances` 时才会保留。

此外，workspace 还通过一个队列管理 instance 的申请和归还，让 executor 能够安全复用已经准备好的模型副本。

### 4. ExecutionServices

`runtime.services.ExecutionServices` 会基于 `RunConfig` 构建出具体的服务依赖图。

当前会装配这些组件：

- `FunctionManager`
- `ParamSpace`
- `ParamWritePlan`
- `ParamApplier`
- `SeriesPlan`
- `ObsStore`
- `SubprocessRunner`
- `SeriesExtractor`
- `Evaluator`

这是一组供 `Executor` 使用的内部依赖集合。

### 5. Executor

`runtime.executor.Executor` 是执行阶段的核心编排组件。

它负责：

- 接收一批输入向量 `X`
- 根据 `cfg.basic.parallel` 决定串行或并行执行
- 把目标值和约束值收集成数组
- 当必须输出缺失时应用 penalty
- 把每次运行的记录提交给 reporter

`_run_one()` 的核心流程如下：

```text
申请一个 workspace instance
  -> 写入参数
  -> 运行外部模型命令
  -> 提取序列
  -> 计算派生量 / objectives / constraints / diagnostics
  -> 归还 workspace instance
  -> 如有错误则应用 on_error 默认值
  -> 把记录提交给 reporter
```

### 6. 参数写入

参数处理被拆成了几个独立部分：

- `ParamSpace` 暴露面向优化器的参数元信息，例如上下界
- `ParamWritePlan` 负责解析物理参数该如何写入
- `ParamApplier` 负责把输入向量映射成物理值，并写入模型输入文件

这个拆分让“优化器看到的参数空间”和“底层文件写入细节”保持分离。

### 7. 模型执行

HydroPilot 当前通过 `SubprocessRunner` 运行外部模型。

在这一层，HydroPilot 本身不做模型计算，它只负责：

- 准备隔离的工作副本
- 在工作副本中执行配置指定的命令
- 把输出文件的读取留给后续提取阶段

### 8. 序列提取

序列相关逻辑目前围绕以下组件组织：

- `SeriesPlan` 负责提取规划
- `ObsStore` 负责观测数据加载和复用
- `SeriesExtractor` 负责提取模拟值和观测值

提取器会把结果写回运行时 context，供后续派生量和目标函数引用。

### 9. 评估计算

`evaluation.evaluator.Evaluator` 消费运行时 context，并产出：

- 派生量
- objectives
- constraints
- diagnostics

这里有几个重要行为：

- 被 objective 或 constraint 依赖的派生量被视为 fatal dependency
- 只被 diagnostic 使用的派生量失败时会降级为 warning
- diagnostics 采用 warning 语义，并在失败时回退到配置里的 `on_error` 值

这使得 HydroPilot 能区分“会使当前运行失效的错误”和“应该记录但不必终止流程的问题”。

## 运行时 Context 与错误处理

每一次运行在内部都表示为一个可变的 context 字典。

初始化时它包含这些信息：

- 输入向量 `X`
- 运行序号 `i`
- batch id
- warnings 列表

随着运行推进，context 会逐步补充：

- 物理参数值
- 提取出的序列
- 派生量
- objective、constraint、diagnostic 标量值
- warning 或 fatal error 对象

HydroPilot 使用 `runtime.errors.RunError` 表示领域内可理解的运行时失败。

executor 会区分：

- 预期内的运行失败，即 `RunError`
- 非预期的 Python 异常，这类异常会被包装成一个 fatal `RunError`

如果一次运行以错误结束：

- workspace instance 仍然会被归还
- objectives、constraints、diagnostics 会按配置填充 `on_error` 默认值
- 只要 reporter 还能工作，这条运行记录仍然会被提交并落盘

这种设计偏向批量稳健性，也就是单个样本失败不应该自动阻断整个批次。

## 报告与持久化

`reporting.reporter.RunReporter` 通过后台线程异步持久化运行产物。

默认会写入运行目录下的 `archive/`：

- `results.db`
- `summary.csv`
- `error.jsonl`
- `error.log`
- 每个输出序列对应的 CSV 文件

reporter 从 executor 接收运行记录，并按批次刷新到磁盘。

这套设计有几个关键特点：

- 模型执行与磁盘写入解耦
- 失败运行也可以被记录
- 结果既可以通过 SQLite 读取，也可以直接看平面文件

reporter 还会尽量保证同一批次内的结果顺序，即使执行阶段开启了并行。

## 并行执行模型

HydroPilot 当前是在“run 级别”做并行。

- `cfg.basic.parallel` 控制 executor 使用多少个 worker 线程
- workspace 会预先创建相同数量的隔离项目副本
- 每次运行会申请一个 instance 目录，在里面执行完成后再归还

这样可以避免多个 worker 同时写同一个模型目录。

因此当前并发模型可以概括为：

```text
并行线程
  -> 各自使用隔离的 instance 目录
  -> 每个活动 run 对应一个外部模型进程
  -> 再加一个异步 reporter 线程
```

## 扩展点

当前架构里已经明确暴露出几个扩展缝隙。

### Templates

新的模型族可以通过 `ModelTemplate` 和模板注册表接入。

模板的职责是把模型专属配置形态转换成统一的 general 配置。

### Writers 与 readers

参数 writer 和序列 reader 都是按类型分发的。

这让 HydroPilot 可以在不改顶层运行链路的前提下支持新的文件格式。

### Functions

派生量和评估计算依赖 `FunctionManager`，它支持内置函数和外部函数。

这让 objective 逻辑不必耦合在 executor 中，扩展方式也更偏声明式。

### Runners

当前运行时使用的是 `SubprocessRunner`，但 runner 抽象为后续替换执行后端留了空间。

## 设计意图

从高层看，这套架构把职责拆成了四层：

- 配置准备层：把 YAML 转成经过校验的运行时数据
- 编排层：负责 run 生命周期和批量调度
- 服务层：负责写入、执行、读取和计算等具体工作
- 报告层：负责持久化产物和诊断信息

这种拆分让 HydroPilot 可以同时支持两种使用方式：

- 轻量的 validation-only CLI
- 可重复调用的 Python 运行时接口

## 阅读建议

如果你第一次阅读代码，建议按这个顺序看：

1. `src/hydro_pilot/api/sim_model.py`
2. `src/hydro_pilot/config/loader.py`
3. `src/hydro_pilot/runtime/session.py`
4. `src/hydro_pilot/runtime/executor.py`
5. `src/hydro_pilot/runtime/services.py`
6. `src/hydro_pilot/reporting/reporter.py`

如果你是在排查配置问题，建议从这里开始：

1. `src/hydro_pilot/validation/entry.py`
2. `src/hydro_pilot/validation/general.py`
3. `src/hydro_pilot/config/loader.py`
4. `src/hydro_pilot/models/swat/validate.py`
