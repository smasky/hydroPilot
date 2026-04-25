# HydroPilot 教程

这是一篇面向当前代码库的中文上手教程。它的目标不是逐字段解释所有配置，而是带你理解：

- HydroPilot 解决的是什么问题
- 一份配置是如何被校验、加载和运行的
- 你应该先学会哪些最关键的工作流
- 出错时应该去哪里看日志和结果

本文会明确区分两类场景：

- 任何人都可以立即操作的内容，例如安装、配置校验、阅读配置结构
- 需要你已经有外部模型工程的内容，例如真正调用 `SimModel` 执行外部模型

## 1. 教程目标

读完这篇教程后，你应该能做到下面几件事：

- 安装并加载当前仓库
- 理解 `general` 模式和模板模式的区别
- 使用 `hydropilot-validate` 校验配置
- 用 `SimModel` 驱动一次模型运行
- 在运行后查看 `archive/` 目录中的结果和错误日志

如果你更想了解内部结构，而不是上手使用，请直接读 [architecture.zh-CN.md](/e:/hydroPilot/docs/architecture.zh-CN.md:1)。

## 2. 环境准备

HydroPilot 当前要求：

- Python 3.10+
- 一个可用的本地 Python 环境
- 当你要真正运行模型时，还需要一个已经准备好的模型工程目录

在仓库根目录执行安装：

```bash
pip install -e .
```

如果你还需要跑测试：

```bash
pip install -e .[dev]
```

如果你需要 UQPyL 集成：

```bash
pip install -e .[uqpyl]
```

### Windows 用户的一个常见问题

这个项目使用 `src` 布局，所以如果你没有安装项目，直接执行：

```bash
python -m hydro_pilot.cli.validate ...
```

很可能会遇到：

```text
ModuleNotFoundError: No module named 'hydro_pilot'
```

最稳妥的方式还是先执行：

```bash
pip install -e .[dev]
```

## 3. 先用 5 分钟理解基本工作流

HydroPilot 当前最值得先掌握的不是“所有字段怎么写”，而是这两个入口：

- `hydropilot-validate`
- `SimModel`

你可以把它们理解成两条不同的链路：

```text
校验链路
  YAML -> prepare_config() -> diagnostics
```

```text
运行链路
  YAML -> load_config() -> SimModel -> Session -> Executor
```

这意味着：

- 先做配置校验是推荐流程
- CLI 校验和直接运行会复用同一套底层配置准备逻辑
- 但 CLI 会打印 diagnostics，而直接运行通常会抛异常

## 4. 第一个练习：先学会校验配置

在真正运行外部模型之前，最安全的第一步是先校验配置。

仓库已经提供了若干示例配置，例如：

- `examples/test_daily.yaml`
- `examples/test_monthly.yaml`
- `examples/test_monthly_complex.yaml`

你可以先执行：

```bash
hydropilot-validate examples/test_daily.yaml
```

或者：

```bash
python -m hydro_pilot.cli.validate examples/test_daily.yaml
```

### 这一步能帮你做什么

它会检查：

- YAML 是否能正常解析
- `version` 是否可识别
- 模板能否正常展开
- `basic`、`parameters`、`series`、`functions` 等结构是否合法
- 观测数据路径是否可解析

### 这一步不能替代什么

它不能保证：

- 你的外部模型命令一定能正常启动
- 模型一定会产生你期望的输出文件
- 提取逻辑一定能读到有效的模拟结果

换句话说，`validate` 通过说明“配置在结构上成立”，但不等于“运行一定成功”。

## 5. 理解一份配置长什么样

HydroPilot 当前有两种主要配置模式：

- `version: general`
- `version: swat`

### 5.1 General 模式

`general` 是运行时真正面对的标准配置形态。你可以把它理解为“完整展开后的标准工作流描述”。

一个最小 general 示例大致如下：

```yaml
version: general

basic:
  projectPath: ./project
  workPath: ./work
  command: my_model.exe

parameters:
  design:
    - name: K
      bounds: [0.0, 1.0]
  physical:
    - name: K
      mode: v
      writerType: fixed_width
      file:
        name: model.inp
        line: 12
        start: 1
        width: 10
        precision: 4

series:
  - id: flow
    sim:
      readerType: text
      file:
        name: model.out
        rowRanges:
          - [1, 365]
        colNum: 2
    obs:
      readerType: text
      file:
        name: obs_flow.txt
        rowRanges:
          - [1, 365]
        colNum: 2

functions:
  - name: NSE
    kind: builtin

derived:
  - id: nse_flow
    call:
      func: NSE
      args: [flow.sim, flow.obs]

objectives:
  - id: obj_nse
    ref: nse_flow
    sense: max
```

你现在不需要记住每个字段，只需要先理解这个结构的分工：

- `basic`：项目目录、工作目录、外部命令
- `parameters`：设计变量和物理写入规则
- `series`：模拟值和观测值从哪里来
- `functions`：可调用函数
- `derived`：派生量计算
- `objectives` / `constraints` / `diagnostics`：真正输出给优化或记录系统的量

### 5.2 模板模式

如果你使用类似 `version: swat` 的模板模式，配置会先经过模板展开，再变成标准的 `general` 配置。

这意味着：

- 模板模式是“更短的模型专属写法”
- `general` 模式是“真正进入运行时的标准形态”

当你通过 `load_config()` 加载配置时，HydroPilot 还会在原 YAML 同目录生成一个：

```text
<原文件名>_general.yaml
```

这个文件非常适合调试。对于模板配置，它能让你看见模板到底展开成了什么；对于已经是 `version: general` 的配置，它能让你看见运行时解析后补全了哪些默认值。

## 6. 从零理解最重要的几个配置块

这一节不追求完整字段手册，只讲上手时最重要的块。

### 6.1 `basic`

`basic` 定义运行时的最小上下文：

```yaml
basic:
  projectPath: ./project
  workPath: ./work
  command: my_model.exe
  keepInstances: false
```

这三个字段都很关键：

- `projectPath`：原始模型工程目录
- `workPath`：HydroPilot 创建临时运行目录的位置
- `command`：在每个运行实例目录里启动的外部命令
- `keepInstances`：是否在运行结束后保留 `instance_*` 临时目录，默认 `false`

默认情况下，HydroPilot 会在 `Session.close()` 或进程退出时清理 `instance_*` 目录，只保留 `archive/` 中的结果、配置副本和错误日志。调试参数写入、模型中间文件或外部程序失败现场时，可以临时设置：

```yaml
basic:
  keepInstances: true
```

调试结束后建议改回默认值，避免模型工程副本长期占用磁盘。

当前版本里，`command` 可以写成：

- 字符串
- 字符串数组

如果你的命令包含空格路径或复杂参数，推荐优先使用数组形式。

### 6.2 `parameters`

`parameters` 分成两层：

- `design`：优化器看到的变量空间
- `physical`：这些变量最终怎样写入模型输入文件

也就是说，HydroPilot 不直接把优化变量塞给模型，而是先经过参数映射与写入逻辑。

如果某个设计变量是离散的，可以在 `design` 层写成：

```yaml
parameters:
  design:
    - name: landuse_code
      type: discrete
      bounds: [1, 3]
      sets: [1, 2, 3]
```

这类变量会在 UQPyL 集成中映射为 `varType=2`，同时 `sets` 会作为 UQPyL `Problem` 的 `varSet` 传入。

当前需要注意两个边界：

- `sets` 目前只支持数值型候选集，例如 `[1, 2, 3]` 或 `[0.1, 0.2, 0.5]`
- 字符串类别候选值暂不直接支持，例如 `["low", "medium", "high"]`；如果需要这类语义，建议先用数值编码，再在参数转换函数中解释这些编码

### 6.3 `series`

`series` 定义如何提取模拟值和观测值。

最常见的情况是：

- `sim` 从模型输出文件中读取
- `obs` 从配置目录附近的观测文件读取

这里一个很重要的路径语义是：

- `obs.file` 这类观测文件按配置文件目录解析
- `sim.file` 这类模拟输出文件按运行时 instance 目录解析

所以如果你的模型会在运行目录里产生 `output.rch`，配置通常应该写成：

```yaml
sim:
  readerType: text
  file: output.rch
  rowRanges:
    - [1, 365]
  colNum: 1
```

而不是写成相对于 YAML 位置的路径。

### 6.4 `functions`、`derived`、`objectives`

这三层可以这样理解：

- `functions`：有哪些函数可以调用
- `derived`：如何用函数和已有上下文算出中间结果
- `objectives`：哪些结果真正作为目标输出

一个典型例子是：

```yaml
functions:
  - name: NSE
    kind: builtin

derived:
  - id: nse_flow
    call:
      func: NSE
      args: [flow.sim, flow.obs]

objectives:
  - id: obj_nse
    ref: nse_flow
    sense: max
```

## 7. 第二个练习：学会看校验错误

在开发配置时，最值得先学的是“读懂 diagnostics”。

例如，如果你漏掉了观测列位置，校验器会给出类似这样的提示：

- 路径：`series[flow].obs`
- 错误：缺少列位置
- 建议：补 `colSpan` 或 `colNum`

这类错误通常包含三部分信息：

- `path`：问题出在配置的哪个位置
- `message`：具体出了什么错
- `suggestion`：建议你怎么修

推荐的工作流是：

1. 先让 `hydropilot-validate` 通过
2. 再去运行外部模型
3. 运行失败时再排查 subprocess、输出文件和提取逻辑

## 8. 真正运行前，你需要知道的边界

这一点非常重要。

仓库中的 SWAT 示例，例如 `examples/test_daily.yaml`，并不是“任何人克隆仓库后立刻就能运行”的自包含示例。它们通常依赖：

- 你本地已有的模型工程目录
- 正确的外部可执行程序
- 与配置匹配的输入输出文件结构

所以你需要区分两类动作：

### 可以直接做的

- 安装项目
- 校验配置
- 阅读模板展开后的 `_general.yaml`
- 阅读代码和文档

### 需要你已有模型工程才能做的

- 调用 `SimModel(...).run(...)`
- 真正运行 `command`
- 从模型输出文件提取模拟值

## 9. 用 Python 驱动运行

当你已经有了可运行的模型工程后，可以通过 `SimModel` 使用 HydroPilot。

典型用法如下：

```python
import numpy as np
from hydro_pilot import SimModel

X = np.array([
  [50.0, 0.5, 100.0],
])

with SimModel("examples/test_monthly.yaml") as model:
  result = model.run(X)
  print(result.objs)
  print(result.cons)
```

### `run(X)` 的输入是什么

`X` 是一个二维数组：

- 每一行表示一次待评估的输入向量
- 每一列对应一个 design parameter

也就是说，如果你有 3 个设计变量，1 组样本，`X.shape` 通常应该是：

```text
(1, 3)
```

### 返回值是什么

返回值是一个字典，当前最重要的是：

- `objs`
- `cons`

其中：

- `objs` 是目标函数数组
- `cons` 是约束数组；如果没有约束，通常是 `None`

## 10. 一次运行里到底发生了什么

当你调用 `model.run(X)` 时，HydroPilot 大致会执行这条链路：

```text
SimModel
  -> Session
  -> Workspace
  -> Executor
  -> ParamApplier
  -> SubprocessRunner
  -> SeriesExtractor
  -> Evaluator
  -> RunReporter
```

可以把它理解成下面这个顺序：

1. 创建隔离的运行目录
2. 把原始模型工程复制成一个或多个 instance
3. 把当前输入向量写入模型输入文件
4. 启动外部命令
5. 从输出文件提取模拟结果
6. 计算派生量、目标、约束和诊断项
7. 把结果和错误记录写入 `archive/`

## 11. 看懂 `archive/` 目录

每次运行结束后，最值得看的目录是：

```text
<runPath>/archive/
```

里面通常会包含：

- `results.db`
- `summary.csv`
- `error.jsonl`
- `error.log`

如果配置启用了某些输出序列，还可能有：

- `<series_id>_sim.csv`

### 11.1 `results.db`

这是 SQLite 数据库，适合后续程序化分析。

### 11.2 `summary.csv`

这是最容易人工快速查看的汇总表。

### 11.3 `error.jsonl`

适合做机器处理或后续检索。

### 11.4 `error.log`

适合人工顺着时间线看错误。

### 11.5 `archive/runner_failures/`

如果某次外部命令执行失败，HydroPilot 现在会把 runner 的日志归档到：

```text
archive/runner_failures/
```

文件名采用扁平形式：

```text
<batch_id>_<run_id>.stdout.log
<batch_id>_<run_id>.stderr.log
```

例如：

```text
archive/runner_failures/2_5.stdout.log
archive/runner_failures/2_5.stderr.log
```

这通常是排查 subprocess 问题时最直接的入口。

## 12. validation 通过了，为什么运行还是会失败

这是最常见的困惑之一。

原因是 `validate` 和 `run` 解决的问题不同。

`hydropilot-validate` 主要验证的是：

- 配置结构是否正确
- 路径语义是否成立
- 模板能否展开
- reader / writer 规格是否合理

而真正运行时还会涉及：

- 外部命令能否启动
- 模型是否会产生预期输出文件
- 输出文件格式是否和提取规则匹配
- 某些派生量和评估函数是否拿到了需要的数据

所以最稳妥的理解是：

- `validate` 通过，只代表“配置结构上成立”
- `run` 成功，才代表“整条运行链路真的跑通”

## 13. 常见问题

### 13.1 `ModuleNotFoundError: No module named 'hydro_pilot'`

通常是因为你还没有安装当前项目。

建议先执行：

```bash
pip install -e .[dev]
```

### 13.2 `command` 应该怎么写

当前版本支持：

- 简单字符串，例如 `swat.exe`
- 字符串数组，例如 `["python", "run_model.py"]`

如果路径中有空格，或命令参数比较复杂，建议优先用数组形式。

### 13.3 为什么外部程序找不到

你需要检查几件事：

- 程序是否真的存在于运行实例目录里
- 是否写了绝对路径
- 是否依赖系统 `PATH`
- 在 Windows 下路径和引号是否正确

### 13.4 为什么失败日志在 `archive/runner_failures/`

因为运行实例目录 `instance_*` 在生命周期结束后通常会被复用或清理，所以失败日志需要额外归档，避免被后续运行覆盖。

## 14. 下一步建议

学完这篇教程后，建议你继续看下面几类文档：

- 架构文档：[architecture.zh-CN.md](/e:/hydroPilot/docs/architecture.zh-CN.md:1)
- 英文版本教程：后续可与中文教程保持同构
- 未来的配置参考文档：适合逐字段查阅

如果你接下来要真正开始写配置，我建议遵循这个顺序：

1. 先从一个最小 `general` 配置开始
2. 先让 `hydropilot-validate` 通过
3. 再确认外部模型工程和 `command` 可独立运行
4. 最后再用 `SimModel.run()` 接进批量评估或优化流程



