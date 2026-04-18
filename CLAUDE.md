# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

hydroPilot 是一个面向水文模型的编排框架，用于将 SWAT、APEX、HBV、VIC 等外部模型与参数优化、不确定性分析流程耦合。核心执行链路为：

配置加载 → 参数写入 → 模型执行 → 结果提取 → 指标评估 → 结果记录

该项目是**配置驱动**的：用户主要通过 YAML 描述实验流程；模型差异通过模板、reader、writer、runner 等可替换组件隔离在主流程之外。

## 常用命令

### 安装项目

```bash
pip install -e .
```

### 安装开发依赖

```bash
pip install -e .[dev]
```

### 安装可选的 UQPyL 集成依赖

```bash
pip install -e .[uqpyl]
```

### 运行全部测试

```bash
pytest
```

### 运行单个测试文件

```bash
pytest tests/test_xxx.py
```

### 按名称过滤运行测试

```bash
pytest tests/test_xxx.py -k case_name
```

## 架构总览

### 主执行入口

`SimModel` 是整个运行流程的主控入口。它负责加载配置、创建隔离运行目录、调度 `ModelAdapter` 完成模型相关工作，并输出适合优化器消费的目标值与约束值。

`SimModel` 主要负责：
- 加载 YAML 配置
- 在 `workPath/tempRun/...` 下创建运行目录
- 为并行运行复制 `instance_*` 工作副本
- 汇总每次运行的结果与惩罚值
- 将运行记录提交给 reporter
- 在退出时清理实例目录

### 聚合层：ModelAdapter

`ModelAdapter` 是 `SimModel` 与具体实现之间的聚合层，用于统一组装以下能力：
- 参数变换与参数写入
- 模型执行
- 结果提取
- 指标评估

这样 `SimModel` 可以保持稳定，而模型差异则通过底层实现扩展。

### 配置加载模式

`load_config()` 支持两种配置模式：

- `version: "general"`：直接解析为内部标准配置
- 其他模板版本（如 `swat`）：先将简化配置展开为标准 general 配置，再继续执行

当模板模式展开配置时，会在源 YAML 同目录下生成 `<原文件名>_general.yaml`，便于检查模板展开后的真实配置。

## 参数链路

hydroPilot 将优化空间参数与模型物理参数分开处理：

- **design parameters**：优化器直接操作的变量 `X`
- **physical parameters**：最终写入模型输入文件的参数 `P`

整体链路为：

`X → Transformer → physical parameter vector P → ParamManager → 按文件分发给 writer`

这里有一个重要设计点：

- writer 的分发粒度是**文件级**
- 而不是“整个模型一个 writer”

这样可以支持同一个模型的不同输入文件使用不同格式和不同 writer 实现。

当前内置参数写入路径为：
- `ParamManager` 按目标文件对物理参数分组
- 每个文件当前由 `FixedWidthWriter` 负责写入

## 模型执行链路

当前 runner 层采用基于子进程的执行方式：

- `ModelAdapter.run_model()` 调用 `SubprocessRunner`
- 执行命令来自 `cfg.basic.command`
- 模型是在复制出来的隔离工作目录中执行，不直接污染原始项目目录

排查输出文件、运行副作用、并行冲突时要优先记住这一点。

## 结果提取链路

`SeriesExtractor` 负责构建评估所需的上下文数据，包括 simulation 序列和 observation 序列：

- obs 序列在初始化阶段按配置读取一次
- sim 序列在每次运行后从输出文件中提取
- series 既可以来自文件，也可以由函数调用生成

当前内置 reader 主要是基于文本文件的提取逻辑。

## 评估链路

`Evaluator` 负责计算：

- derived
- objectives
- constraints
- diagnostics

其中有一个很重要的实现细节：

- 若某个 derived 被 objective 或 constraint 依赖，则其失败属于**致命失败**
- 若某个 derived 只被 diagnostic 使用，则其失败只记为 **warning**，并回退到 `on_error`

修改 derived 依赖关系时，要特别注意这条规则，因为它会直接影响运行失败与否。

## 结果记录与持久化

`RunReporter` 是一个异步结果记录层，会在运行目录下的 backup 目录中写出：

- `results.db`
- `summary.csv`
- `error.jsonl`
- `error.log`
- 可选的序列 CSV 导出文件

reporter 通过后台线程异步消费运行记录，因此结果持久化与模型执行本身是解耦的。

## 关键代码位置

- `hydro_pilot/sim_model.py`：主控入口
- `hydro_pilot/adapter/adapter.py`：聚合层
- `hydro_pilot/config/loader.py`：配置加载与模板展开
- `hydro_pilot/params/manager.py`：参数管理、变换与按文件分发写入
- `hydro_pilot/runner/subprocess_runner.py`：外部模型执行
- `hydro_pilot/series/extractor.py`：序列提取与依赖解析
- `hydro_pilot/evaluation/evaluator.py`：derived / objective / constraint / diagnostic 计算
- `hydro_pilot/reporting/reporter.py`：异步结果持久化
- `hydro_pilot/templates/`：模型模板系统，当前 SWAT 是最完整的内置模板实现

## 项目约束

- 忽略 `.history/` 下的文件
- 与 Claude 相关的项目文件都放在 `.claude/` 下
- 代码注释使用英文
- 项目技术文档放在 `.claude/memory/`
- 代码中的标识符使用驼峰命名
- 文件名使用下划线分词
- 讨论类文档使用中文
- 动手修改项目文件前，先和用户确认，不要直接改动

## 当前项目方向

当前代码结构明确围绕以下原则构建：

- 主编排流程保持稳定
- 模型差异下沉到 template / reader / writer / runner
- 将优化语义与模型文件编辑语义分离

目前 SWAT 是仓库里完成度最高的内置模板，但整个框架的目标始终是支持多个水文模型共用同一套编排主流程。
