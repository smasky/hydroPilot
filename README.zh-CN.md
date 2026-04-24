[English](./README.md) | [简体中文](./README.zh-CN.md)

# HydroPilot

> 一个面向水文模型率定、评估与优化的配置优先编排框架。

HydroPilot 希望把水文建模周边那些重复的胶水代码收敛成一条可复用工作流：参数映射、输入写入、模型执行、结果提取、目标计算与运行记录。

它的核心是模型无关的。就当前仓库而言，SWAT 是第一个内置模板，也是目前最成熟的集成。

## HydroPilot 是什么

HydroPilot 是：

- 一个由配置驱动的工作流框架
- 一个面向重复模型实验的可复用运行时
- 一个不绑定单一模型家族的通用 schema
- 一个可以让特定模型更容易接入的模板体系

HydroPilot 不是：

- 一个只服务于 SWAT 的脚本集合
- 一个单独的优化器
- 一个已经把所有模型模板都做完的多模型平台

## 当前状态

当前代码里已经具备的能力：

- `version: general` 通用工作流模式
- `version: swat` 模板模式
- fixed-width 参数写入
- 基于文本的序列提取
- 基于子进程的模型执行
- 内置与外部评估函数
- SQLite 与 CSV 结果记录
- UQPyL 集成
- `hydropilot-validate` CLI

目前应视为规划中、而不是已内置支持的内容：

- APEX
- HBV
- VIC
- HEC-HMS

## 为什么要做这个

在很多水文率定任务里，真正麻烦的往往不是优化算法本身，而是围绕它的一圈脚本工作：

- 把优化变量映射到物理参数
- 把参数写入多个模型输入文件
- 安全地重复启动外部模型
- 提取可比较的输出序列
- 计算目标、约束和诊断量
- 保留运行记录以便排错和比较

HydroPilot 的目标，就是把这些重复劳动收敛成一条可复现的统一流水线。

## 两种配置模式

### 1. General mode

当你希望完整控制一个模型无关的工作流时，使用 `version: general`。

- 参数写入方式由你显式定义
- 序列 reader 由你显式定义
- 这是框架真正的核心层

### 2. Template mode

当你希望写更短的模型特定配置时，使用类似 `version: swat` 这样的模板版本。

- 模板会把紧凑配置展开成标准 general 配置
- 真正的运行时执行仍然走同一套 general 流水线
- 在当前代码库里，`swat` 是唯一内置模板

## 安装

需要 Python 3.10+。

以 editable 方式安装：

```bash
pip install -e .
```

安装开发依赖：

```bash
pip install -e .[dev]
```

安装 UQPyL 集成所需依赖：

```bash
pip install -e .[uqpyl]
```

## 快速开始

### 校验配置文件

```bash
hydropilot-validate path/to/config.yaml
```

### 使用 `SimModel` 评估参数向量

```python
import numpy as np
from hydro_pilot import SimModel

X = np.array([
    [50.0, 0.5, 100.0],
])

with SimModel("examples/test_monthly.yaml") as model:
    result = model.evaluate(X)
    print(result["objs"])
```

### 与 UQPyL 配合使用

```python
from hydro_pilot.integrations import UQPyLAdapter
from UQPyL.optimization import DE

with UQPyLAdapter("examples/test_daily.yaml") as problem:
    optimizer = DE(problem)
    optimizer.run()
```

## 最小 general 示例

下面这个例子比旧草稿更贴近当前真实 schema：

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
        rowRanges: [[1, 365]]
        colNum: 2
    obs:
      readerType: text
      file:
        name: obs_flow.txt
        rowRanges: [[1, 365]]
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
  items:
    - id: obj_nse
      ref: nse_flow
      sense: max
```

## 模板示例

仓库里目前可以直接参考的 SWAT 示例包括：

- `examples/test_daily.yaml`
- `examples/test_monthly.yaml`
- `examples/test_monthly_complex.yaml`
- `examples/test_monthly_series.yaml`

一个紧凑的 SWAT 配置大致如下：

```yaml
version: swat

basic:
  projectPath: E:\BMPs\TxtInOut
  workPath: ./work
  command: swat.exe

parameters:
  design:
    - name: CN2
      bounds: [35, 98]
    - name: ALPHA_BF
      bounds: [0, 1]
    - name: GW_DELAY
      bounds: [0, 500]

series:
  - id: flow
    sim:
      file: output.rch
      id: 62
      period: [2019, 2021]
      timestep: monthly
      colSpan: [50, 61]
    obs:
      file: obs_flow_monthly.txt
      rowRanges: [[1, 36]]
      colSpan: [1, 12]

functions:
  - name: NSE
    kind: builtin

derived:
  - id: nse_flow
    call:
      func: NSE
      args: [flow.sim, flow.obs]

objectives:
  items:
    - id: obj_nse
      ref: nse_flow
      sense: max
```

## 路径语义

这一点在当前实现里很重要：

- 观测文件，比如 `obs.file`，按配置文件所在位置解析
- 模拟输出文件，比如 `sim.file`，按运行时 project 副本 / work instance 解析

所以如果模型在运行目录里生成 `output.rch`，配置通常应保持为：

```yaml
sim:
  readerType: text
  file: output.rch
```

而不是写成相对于 YAML 文件位置的路径。

## 运行链路

HydroPilot 现在有两条值得分开理解的链路。

### 配置与模板链路

```text
YAML config
  -> config.loader
  -> template registry (if version != general)
  -> template expansion to general config
  -> RunConfig
```

例如，`version: swat` 会先经过 SWAT 模板展开，然后变成标准的 `version: general` 运行时配置。

### 运行时执行链路

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

从概念上看，运行时流水线就是：

```text
Parameter writing
  -> Model execution
  -> Series extraction
  -> Derived/objective evaluation
  -> Run reporting
```

## 仓库结构

```text
src/hydro_pilot/
  api/           公共 API 入口
  cli/           命令行入口
  config/        配置加载、schema、路径解析
  evaluation/    函数注册与标量评估
  integrations/  外部优化器适配
  io/            readers、writers、runners
  models/        模板注册与模型特定知识
  params/        参数空间与写入应用
  reporting/     运行记录与产物持久化
  runtime/       session、workspace、执行编排
  series/        序列规划、obs store、提取
  validation/    面向用户的配置诊断
```

## 内置函数

当前内置函数包括：

- `NSE`
- `KGE`
- `R2`
- `RMSE`
- `MSE`
- `PBIAS`
- `LogNSE`
- `sum_series`

同时也支持外部 Python 函数。

## 输出与运行记录

每次运行都会创建独立的 runtime workspace 和 backup 目录。根据配置和执行路径，产物可能包括：

- 原始配置副本
- 展开后的 general 配置副本
- 复制后的观测文件
- `summary.csv`
- `results.db`
- `error.jsonl`
- `error.log`
- 可选的序列导出 CSV

## CLI 现状

目前文档里可以明确承诺的内置 CLI 只有：

- `hydropilot-validate`

像 `run`、`expand` 这样的命令，现阶段更适合继续放在 roadmap，而不是写成已经存在的正式入口。

## 支持矩阵

| 能力 | 状态 |
|---|---|
| General 配置模式 | 已可用 |
| Template 系统 | 已可用 |
| 当前内置注册模板 | SWAT |
| Fixed-width 参数写入 | 已可用 |
| 文本序列提取 | 已可用 |
| Subprocess runner | 已可用 |
| SQLite + CSV 结果记录 | 已可用 |
| UQPyL adapter | 已可用 |
| APEX 模板 | 规划中 |
| HBV 模板 | 规划中 |
| VIC 模板 | 规划中 |
| HEC-HMS 模板 | 规划中 |

## Roadmap

### 近期

- 改善 README 和上手引导
- 增加更完整的 CLI 工作流，例如 `run` 和 `expand`
- 强化测试与跨平台行为
- 补充更多示例

### 中期

- 正式化模板、reader、writer、runner 的扩展契约
- 增加 fixed-width 之外的 IO 协议
- 改进实验元数据与结果检查体验

### 长期

- 支持更多水文模型模板
- 支持更多执行后端
- 演进为更完整的实验管理平台

## 项目总结

HydroPilot 已经拥有一套可用的编排核心，也已经有了真正可运行的 SWAT 集成。下一步更关键的，不是再重新发明运行时，而是让这个框架更容易理解、更容易扩展，也更容易被别人拿来直接用。
