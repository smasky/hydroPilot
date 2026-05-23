# HydroPilot 文档

HydroPilot 是一个配置优先的水文模型率定、评估与优化编排框架。

说明：

- `docs/` 根目录以英文文档为主。
- 中文文档统一放在 `docs/cn/` 下，作为辅助阅读入口。

## 文档导航

### 核心参考

- [架构设计](architecture.md) — 配置链路、运行链路、模块布局与执行模型
- [教程](tutorial.md) — 面向当前代码库的中文上手教程
- [CLI 参考](cli.md) — `hydropilot-validate`、`hydropilot-test`、`hydropilot-apply`、`hydropilot-run` 四个命令行工具
- [配置参考](configuration-reference.md) — 所有配置字段的逐项说明
- [示例](examples.md) — 示例配置索引与导读
- [Python API](python-api.md) — `SimModel`、`BatchRunResult`、`UQPyLAdapter`
- [UQPyL 集成](uqpyl.md) — 与 UQPyL 优化器的桥接说明

### General 模式

- [配置参考](configuration-reference.md) — 完整的 `version: general` schema、路径语义与运行字段
- [示例](examples.md) — 包含 general 模式示例及与模板模式的对照

### SWAT 2012

- [SWAT 2012 模板](templates/swat-2012.md) — `version: swat` 配置、参数库与输出变量
- [SWAT 2012 日尺度快速上手](guides/swat-daily-step-by-step.md) — 第一个可运行的 SWAT 2012 工作流
- [SWAT 2012 月尺度指南](guides/swat-monthly-guide.md) — 将同一工作流迁移到月尺度输出
- [SWAT 2012 参数与序列](guides/swat-parameters-and-series.md) — 输出文件、变量、过滤与参数策略

### SWAT+

- [SWAT+ 模板](templates/swatplus.md) — `version: swatplus` 配置、参数数据库与输出变量
- [SWAT+ 支持现状](guides/swatplus-support-status.md) — 当前已实现范围与剩余边界
- [SWAT+ calibration.cal 写入链路](guides/swatplus-calibration-cal.md) — SWAT+ 参数如何通过 `calibration.cal` 写入
- [SWAT+ calibration.cal 用户指南](guides/swatplus-calibration-cal-user-guide.md) — 从使用者视角理解这条新写入路线
- [SWAT+ 流量抽取指南](guides/swatplus-flow-extraction.md) — 如何从 SWAT+ 输出文件抽取径流

### XAJ

- [XAJ 模板](templates/xaj.md) — `version: xaj` 配置与工程结构
- [示例](examples.md) — 包含 XAJ 模板示例及其展开后的 general 配置

## 快速链接

- [README](../README.md) — 项目概览、安装与快速开始
- [英文文档首页](../index.md) — 英文主文档入口

## 配置模式

HydroPilot 支持两种配置模式：

- **通用模式**（`version: general`）—— 完全掌控一个与模型无关的工作流。你需要显式定义参数写入规则和序列读取规则。
- **模板模式**—— 更简短的模型专属配置。当前内置模板：SWAT 2012（`version: swat`）、SWAT+（`version: swatplus`）和新安江模型（`version: xaj`）。模板在运行时会自动展开为标准的通用配置格式。

## CLI 工具

HydroPilot 提供四个命令行入口：

| 命令 | 作用 |
|---|---|
| `hydropilot-validate` | 校验配置文件并输出诊断信息 |
| `hydropilot-test` | 用默认参数向量执行一次完整的冒烟测试 |
| `hydropilot-apply` | 将参数应用到工程副本 |
| `hydropilot-run` | 从 run YAML 执行一次单次评估 |

## Python API

公开的主要 API 导出：

| 符号 | 作用 |
|---|---|
| `SimModel` | 模型评估的主要运行时入口 |
| `BatchRunResult` | 批量评估的结果容器 |
| `UQPyLAdapter` | 连接 UQPyL 优化器的适配器 |

导入示例：

```python
from hydropilot import SimModel, BatchRunResult
from hydropilot.integrations import UQPyLAdapter
```
