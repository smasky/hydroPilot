# hydroPilot 架构定调文档

## Context

本文档用于为 hydroPilot 的后续架构演进定调。目标不是直接实现某个具体模型，而是先建立一套**可行、可渐进落地、并且能为最终多模型支持预留空间的主框架**。

hydroPilot 当前已经具备稳定的运行主链路：

配置加载 → 参数写入 → 模型执行 → 结果提取 → 指标评估 → 结果记录

当前主链路已经能支撑以 SWAT 为代表的文本型模型工作流，但在“面向多模型的智能部署”这个更长期目标上，还缺少统一的模型接入框架。尤其在以下方面仍较弱：

- 参数写入主要绑定 `FixedWidthWriter`
- 结果提取主要绑定 `TextReader`
- 模板层虽已有 SWAT，但尚未总结成通用模型接入范式
- NetCDF / NPY / 栅格 / 表格型 I/O 还没有统一抽象

因此，本设计文档的核心任务是回答：

> hydroPilot 应该如何设计一套以 **Discovery + Library + Template Builder + General Config + Runtime** 为主线的模型智能部署框架，使系统能够在不破坏主执行链路的前提下，逐步支持 SWAT、APEX、VIC、XAJ、Noah-MP 等主流水文/陆面模型。

---

## 一、设计目标

### 1. 总目标

建立一套“**模型语义前置、运行时通用**”的架构：

- 用户面向模型语义写配置
- 模型相关知识在模板阶段完成翻译
- 运行时只消费统一的 general config
- 新模型接入主要通过 discovery / library / builder / reader / writer 扩展完成，而不是修改 `SimModel`

### 2. 具体目标

1. **主流程保持稳定**
   - `SimModel -> ModelAdapter -> ParamManager / Runner / SeriesExtractor / Evaluator / Reporter` 主链路不因新模型接入而频繁改动。

2. **模型差异前置到模板阶段**
   - 模型版本、driver 类型、文件结构、变量映射、参数位置等差异，尽量在 runtime 前解决。

3. **I/O 能力按数据介质抽象，而不是按模型抽象**
   - 比如 `fixed_width`、`table`、`key_value`、`yaml`、`netcdf` 等应作为通用能力，而不是写成 `swat_writer`、`vic_reader` 之类的模型特化实现。

4. **General Config 成为唯一运行时边界**
   - 一旦模板展开完成，runtime 不再关心具体模型名，只认统一配置。

5. **先做最小可生长框架，而不是一步到位的大框架**
   - 第一阶段优先补齐 registry、通用 spec、模板三分法；复杂 aggregation、复杂 execution profile 等放在后续演进阶段。

---

## 二、核心设计原则

### 原则 1：模型语义与运行语义分离

用户配置里表达的是模型语义，例如：

- SWAT: `subbasin=5`, `variable=FLOW_OUT`, `period=monthly`
- VIC: `driver=image`, `variable=OUT_RUNOFF`, `cell=[35,42]`
- Noah-MP: `landClass=7`, `variable=SOIL_M`

这些语义不应直接进入 runtime。它们必须先被翻译成统一运行语义，例如：

- `readerType=text`, `rowRanges=[...]`, `colNum=7`
- `writerType=netcdf`, `variable=infilt`, `selector.index={y:35,x:42}`

### 原则 2：runtime 不理解模型，只理解 general config

运行时只消费：

- 参数变换规则
- writerType + writer spec
- readerType + reader spec
- model command
- functions / derived / objectives / diagnostics

runtime 不应再去判断：

- 这是 SWAT 还是 VIC
- 这是 HRU 还是 grid
- `FLOW_OUT` 是什么含义

### 原则 3：registry 只做格式分发，不承载业务语义

registry 的职责非常明确：

- `fixed_width -> FixedWidthWriter`
- `key_value -> KeyValueWriter`
- `text -> TextReader`
- `netcdf -> NetCDFReader`

它只负责根据 type 找到实现，不负责解释模型概念，不负责做复杂模板翻译，也不负责聚合逻辑决策。

### 原则 4：模板负责翻译模型语义，不直接执行 I/O

模板系统负责：

- discovery：发现项目事实
- library：提供模型知识
- builder：把用户语义翻译成 general config

模板不直接 new reader/writer，也不应把具体 I/O 行为硬编码到 runtime 外的临时逻辑里。

### 原则 6：子模型 Template 不是兜底层

子模型 template 的职责，是把**明确支持的模型语义**翻译成 general config，而不是兜底处理所有非 general 配置。

这意味着：

- template 只转换自己明确识别并承诺支持的模型语义糖
- 对未命中模板规则、但 general 可处理的字段，应尽量原样保留并交给 general
- template 不应提前吞掉、改写或猜测不属于自身职责的字段
- general config 才是最终统一的协议边界与兜底校验边界

例如在 SWAT 模板中：
- 命中 `output.rch` / `output.sub` / `output.hru` 这类明确 SWAT 输出语义时，template 负责展开 `rowRanges`、`size` 等运行语义
- 未命中这些模板规则时，应保留为 general extract 语义，而不是由 SWAT template 做隐式兜底解释

---

## 三、主框架总览

推荐的主链路如下：

```text
用户简化 YAML
  ↓
Discovery
  ↓
Model Library
  ↓
Template Builder / Config Expander
  ↓
General Config
  ↓
Runtime
  ├─ Param Transformer: X → P
  ├─ WriterRegistry: writerType → Writer
  ├─ ModelRunner
  ├─ ReaderRegistry: readerType → Reader
  ├─ Evaluator
  └─ Reporter
```

这条链路是后续设计的总定调：

- **前半段解决“用户想表达什么、项目里实际有什么、模型知识怎么翻译”**
- **后半段解决“系统怎么执行”**

---

## 四、五个核心层次

### 1. User Intent Layer

这一层是用户输入层，推荐用户优先写“模型语义”，而不是底层文件定位。

同时保留 `version: general` 作为专家模式，允许用户直接写 runtime 所需的底层 general config。

### 2. Discovery Layer

Discovery 的职责是：**识别项目事实**。

它只回答“这个项目实际上长什么样”，不负责做参数校准决策，也不负责做 I/O 执行。

应覆盖的信息包括：
- 模型版本
- driver 类型
- 项目目录结构
- 参数文件位置
- 输出文件位置
- 子流域 / HRU / 网格 / basin / station 等对象索引
- NetCDF 坐标变量 / mask 文件 / 栅格维度
- 输出时间尺度与文件命名规则

### 3. Model Library Layer

Library 的职责是：**提供模型知识**。

它不扫描具体项目，而是维护该模型的一般性知识和默认规则。

应覆盖的信息包括：
- 参数定义
- 参数默认上下界
- 参数推荐 mode（`r` / `v` / `a`）
- 参数归属文件/变量类型
- 变量定义与映射
- 输出变量默认 readerType
- 典型 writerType / readerType 推荐
- 特定 driver 或模型版本的默认规则

### 4. Template Builder / Config Expander Layer

这是整个“智能部署”框架的核心。

它负责把：
- 用户意图
- discovery 结果
- model library 知识

组合成统一的 **general config**。

Builder 的使命是：
- 把模型语言翻译成运行语言
- 不把这些模型知识泄漏到 runtime

### 5. Runtime Layer

Runtime 只负责执行 general config。

它的职责边界应该保持清晰：
- `Transformer`: `X → P`
- `WriterRegistry`: `writerType → Writer`
- `Runner`: 执行模型
- `ReaderRegistry`: `readerType → Reader`
- `Evaluator`: derived / objectives / constraints / diagnostics
- `Reporter`: 结果记录

runtime 不应负责：
- 再次解释模型语义
- 再次发现项目结构
- 再次推断参数位置

---

## 五、General Config 的定位

General Config 是整个框架最关键的边界对象。

### 它的作用

1. 作为模板阶段的输出
2. 作为 runtime 的唯一输入标准
3. 作为调试、复现、人工检查的中间产物

### 它应具备的特性

- 与模型名解耦
- 与具体模板逻辑解耦
- 对 runtime 足够明确
- 可落盘保存并独立运行

### 原则

所有模板模式最终都应展开为 `version: "general"` 的配置结构。

这意味着：
- 模板只是“配置展开器”
- general config 才是“执行协议”

---

## 六、I/O 能力的抽象策略

### 1. 总体原则

I/O 不按模型分类，而按**数据介质类型**分类。

### 2. Writer 能力族

推荐逐步形成以下 writer 族：

#### 文本类
- `FixedWidthWriter`
- `DelimitedTableWriter`
- `KeyValueWriter`
- `BlockTextWriter`
- `NamelistWriter`

#### 结构化配置类
- `YamlWriter`
- `JsonWriter`

#### 科学数据类
- `NetCDFWriter`
- `NpyWriter`
- `RasterAsciiWriter`

### 3. Reader 能力族

推荐逐步形成以下 reader 族：

#### 文本序列类
- `TextReader`
- `TableReader`
- `SectionTableReader`

#### 科学数据类
- `NetCDFReader`
- `NpyReader`
- `RasterAsciiReader`

#### 可选增强类
- `SpatialAggregateReader`
- `TimeWindowReader`

### 4. registry 的角色

registry 只做：
- `type -> class`

例如：
- `fixed_width -> FixedWidthWriter`
- `table -> TableReader`
- `netcdf -> NetCDFReader`

registry 不承担：
- 模型语义解释
- 模板翻译
- 复杂聚合策略决策

---

## 七、NetCDF 能力的设计立场

NetCDF 是未来支撑 VIC Image、Noah-MP、分布式 XAJ 等模型的关键能力之一。

### 核心判断

可以抽象，但不能抽成“万能 NetCDFWriter/Reader”。

正确的做法是抽成：

1. 通用 NetCDF I/O 内核
2. 通用 selector spec
3. 模板负责把模型语义翻译成 selector spec

### 推荐的最小 selector 能力

#### P0
- `index`：按固定索引选点
- `slice`：按区间选片
- `full`：整变量覆写/读取

#### P1
- `coord`：按坐标定位
- `where` / `mask`：按类别或掩膜定位

### 设计边界

NetCDFWriter / NetCDFReader 不应理解：
- basin 是什么
- HRU 是什么
- landClass 是什么

这些都属于模板和 library 的语义翻译职责。

---

## 八、推荐的最小可落地框架

为了兼顾可实现性与未来扩展空间，不建议一开始搭建过大的 integration framework。推荐采用“**轻骨架 + 强扩展点**”策略。

### 保持稳定不动的部分

- `SimModel`
- `ModelAdapter`
- `Evaluator`
- `RunReporter`

### 第一阶段要做实的扩展点

1. `WriterRegistry`
2. `ReaderRegistry`
3. 模板三分法：`discovery + library + builder`
4. General Config 中显式支持 `writerType` / `readerType`

### 第一阶段只补最有价值的通用能力

#### Writer
- `KeyValueWriter`
- `DelimitedTableWriter`

#### Reader
- `TableReader`

### 第二阶段再补

- `NetCDFWriter`
- `NetCDFReader`
- 必要的 selector spec

### 第三阶段再考虑

- `NpyWriter / NpyReader`
- `RasterAsciiWriter / RasterAsciiReader`
- 更复杂的 aggregation / execution profile

---

## 九、与现有代码的衔接方式

当前代码并不需要推倒重来。推荐采用“小步重构”的方式推进。

### 当前已经具备的基础

- `SimModel` 主流程稳定
- `ModelAdapter` 已有聚合层
- `load_config()` 已支持 template → general
- SWAT 模板已具备 discovery / library / builder 雏形
- 参数变换与 writer 已部分分层
- 结果提取与 reader 已部分分层

### 当前最重要的差距

- writer / reader 仍偏单实现绑定
- general config 对 `writerType` / `readerType` 的表达还不够显式、可扩展
- SWAT 模板还未沉淀成“新模型接入规范”

---

## 十、主设计结论

hydroPilot 后续的模型智能部署框架应明确采用以下主思路：

> **用户面向模型语义写配置；系统通过 Discovery 获取项目事实，通过 Model Library 提供模型知识，再由 Template Builder 将用户语义展开为 General Config；运行时只消费 General Config，通过 Transformer、WriterRegistry、Runner、ReaderRegistry、Evaluator 和 Reporter 完成执行。**

这个结论意味着：

1. 未来的重点不是让 runtime 变得越来越懂模型
2. 而是让模板阶段承担足够的语义翻译职责
3. 同时让 runtime 保持稳定、通用、可扩展

这将成为 hydroPilot 架构演进的总定调。
