[English](./README.md) | [简体中文](./README.zh-CN.md)

# HydroPilot

> 一个面向水文模型率定、评估与优化的声明式实验编排框架。

HydroPilot 是一个**面向多种水文模型的通用框架**。它希望把参数映射、输入写入、模型运行、结果提取、指标评估、目标计算和结果记录，统一抽象成一条由配置驱动的工作流，而不是为每个项目重复编写大量胶水脚本。

## HydroPilot 是什么

HydroPilot 是：

- 一个**面向多模型的水文模拟编排框架**
- 一个**以 YAML 配置为核心**的工作流系统
- 一个可扩展的**模板 / Writer / Reader / Runner / Evaluator** 架构
- 一个目标明确的通用框架：希望支持**多个水文模型**，而不是服务于单一模型

## HydroPilot 不是什么

HydroPilot 不是：

- 一个只服务 SWAT 的参数修改脚本集合
- 一个与某一种模型文件结构强耦合的硬编码流程
- 一个单独的优化算法库
- 一个已经把所有模型模板都实现完毕的平台

SWAT 目前是仓库里**最成熟的内置模板**，也是**第一个完整实现的模板**；但这并不等于 HydroPilot 的定位就是“SWAT 专用工具”。

## 为什么强调配置，而不是脚本？

在很多模型率定任务中，真正反复消耗时间的并不是优化算法本身，而是围绕它的一整圈脚本工作：

- 向多个输入文件写参数
- 安全地重复启动外部模型
- 从模型输出中提取可比较的序列
- 计算指标、目标、约束和诊断量
- 把每次运行结果记录下来并保证可复现

HydroPilot 的目标，就是把这些重复逻辑沉淀为统一框架，让模型率定尽量从“每个项目都写一套脚本”转向“主要通过配置描述实验”。

## 核心概念

### 1. General mode 与 Template mode

HydroPilot 当前有两种主要入口：

- **General mode**：`version: general`
  - 使用通用配置 schema 手动描述整个工作流
  - 这是 HydroPilot 作为“多模型通用框架”的核心能力
- **Template mode**：例如 `version: swat`
  - 由模型模板把简化配置自动展开为标准的 general 配置

这个区分非常重要：HydroPilot 不是由 SWAT 模板定义的，模板只是让某些具体模型更容易接入的一层能力。

### 2. Design space 与 Physical space

HydroPilot 使用两层参数架构：

- **design parameters**：优化器看到的设计变量
- **physical parameters**：真正写入模型输入文件的物理参数

两者之间通过 transformer 建立映射。这样就可以支持：

- 一一映射
- 一对多映射
- 分组映射
- 自定义转换逻辑

### 3. Series、Derived、Objectives、Diagnostics

评估链路被拆成以下几层：

- **series**：提取或计算得到的模拟/观测序列
- **derived**：基于序列进一步计算出的派生量
- **objectives**：暴露给优化器的目标值
- **constraints**：可选的约束项
- **diagnostics**：只用于记录分析、不直接参与优化的诊断量

## 当前仓库状态

从当前代码来看，HydroPilot 已经具备一条完整的主流程：

- 配置加载与校验
- 参数变换与写入
- 基于子进程的模型执行
- 基于文本的序列提取
- 派生量 / 目标 / 约束评估
- SQLite 与 CSV 结果记录
- 面向 UQPyL 的适配入口

但在当前版本里，需要准确说明的是：

- **general 配置模式**：已可用
- **SWAT 模板模式**：已可用
- **当前真正注册的内置模板只有 SWAT**
- APEX / HBV / VIC / HEC-HMS 等模型应表述为**计划支持**，而不是“已经支持”

## 快速开始

### General mode

General mode 是 HydroPilot 的通用配置核心，适合手动接入自定义模型。

下面是一个最小化的示意配置：

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
      file:
        name: model.inp
        line: 12
        start: 1
        width: 10
        precision: 4

series:
  - id: flow
    sim:
      file: model.out
      rowRanges:
        - [1, 365]
      colNum: 2
    obs:
      file: obs_flow.txt
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
  items:
    - id: obj_nse
      ref: nse_flow
      sense: max
```

可以直接通过 `SimModel` 评估一批参数向量：

```python
import numpy as np
from model_driver.sim_model import SimModel

X = np.array([
    [0.5],
])

with SimModel("path/to/general.yaml") as model:
    result = model.evaluate(X)
    print(result["objs"])
```

说明：

- 上面的 general mode 示例主要用于展示通用 schema。
- 在当前仓库中，最完整、最现成的 example 仍然主要集中在 `examples/` 下的 SWAT 示例。

### Template mode

Template mode 用于模型特定集成。当前仓库里真正内置的模板是 `swat`。

仓库中已经存在的一个实际示例如下：

```yaml
version: "swat"

basic:
  projectPath: "E:\\DJBasin\\TxtInOutFSB"
  workPath: "./work"
  command: "swat.exe"

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
    desc: "Daily streamflow at outlet"
    sim:
      file: output.rch
      subbasin: 33
      period: [2010, 2015]
      timestep: daily
      colSpan: [50, 61]
    obs:
      file: obs_flow.txt
      rowRanges:
        - [1, 2191]
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
      desc: "Maximize NSE"
      ref: nse_flow
      sense: max
```

如果要通过 UQPyL 运行优化流程，可以这样调用：

```python
from model_driver.wrappers import UQPyLAdapter
from UQPyL.optimization import DE

with UQPyLAdapter("examples/test_daily.yaml") as problem:
    optimizer = DE(problem)
    optimizer.run()
```

## 当前内置函数

从当前代码实现看，内置函数包括：

- `NSE`
- `KGE`
- `R2`
- `RMSE`
- `MSE`
- `PBIAS`
- `LogNSE`
- `sum_series`

此外也支持通过外部 Python 文件注册自定义函数。

## 当前支持矩阵

| 能力 | 状态 |
|---|---|
| General 配置模式 | 已可用 |
| Template 系统 | 已可用 |
| 当前内置注册模板 | SWAT |
| Fixed-width 参数写入 | 已可用 |
| 基于文本的序列提取 | 已可用 |
| Subprocess runner | 已可用 |
| SQLite + CSV 结果记录 | 已可用 |
| UQPyL adapter | 已可用 |
| APEX 模板 | 计划中 |
| HBV 模板 | 计划中 |
| VIC 模板 | 计划中 |
| HEC-HMS 模板 | 计划中 |

## 架构

```text
Config Loading
  -> Parameter Writing
  -> Model Execution
  -> Result Extraction
  -> Metric / Objective Evaluation
  -> Result Recording
```

```text
SimModel
  └─ ModelAdapter
      ├─ ParamManager
      │   └─ Transformer
      │   └─ ParamWriter
      ├─ ModelRunner
      ├─ SeriesExtractor
      │   └─ SeriesReader
      ├─ Evaluator
      │   └─ FunctionManager
      └─ RunReporter
```

这套架构最核心的思想是：

- 主流程尽量稳定
- 模型差异尽量外置到模板和插件层
- 把优化空间变量与文件空间参数分开
- 让运行过程更容易复现、检查和比较

## 输出与运行记录

每次运行都会创建隔离的工作目录，并在 backup 目录中保留：

- 原始配置文件
- 模板展开得到的 general 配置（如果存在）
- 复制的观测文件（如果适用）
- `summary.csv`
- `results.db`
- `error.jsonl`
- `error.log`

这使得 HydroPilot 已经具备基础但实用的实验追踪能力。

## 安装状态

当前仓库仍然更接近 **source-layout first**：

- 项目名是 **HydroPilot**
- 当前包名仍然是 **`model_driver`**
- 更正式的打包与安装流程（如 `pyproject.toml`、extras、release metadata）应视为近期 roadmap 的一部分

从当前代码依赖看，至少需要一个包含以下库的 Python 环境：

- `numpy`
- `PyYAML`
- `pydantic`

如果要跑优化流程，还需要 `UQPyL`。

## Roadmap

### 近期

- 把对外品牌统一为 **HydroPilot**
- 让 README 与当前代码 API 完全对齐
- 补齐打包元数据和安装说明
- 补强 general mode 与 template mode 的示例
- 增加 `validate` / `run` / `expand` 等 CLI 入口

### 中期

- 增加更多模型模板
- 增加 fixed-width 之外的 Reader / Writer
- 强化测试体系和 schema 文档
- 增加结果读取和实验元数据管理能力

### 长期

- 演进为更完整的多模型水文实验平台
- 支持更多运行后端
- 增加更丰富的实验管理与可视化分析能力

## 项目阶段判断

当前更准确的表述是：

> HydroPilot 已经具备一个面向多模型的通用内核，并且以 SWAT 作为第一个完整实现的模板；它已经是一个很强的研究/工程基础，但仍在向更完整的公开发布形态演进。
