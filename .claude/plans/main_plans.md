# hydroPilot 模型智能部署主设计文档

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

### 原则 5：通用能力优先于模型特例

当新增能力时，优先问：

- 这是一个通用数据介质问题吗？
- 能否抽象成所有模型都能复用的 writer / reader 能力？

而不是优先问：

- 能否先给某个模型写一套特殊逻辑？

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

#### 典型例子

SWAT：
```yaml
version: swat
series:
  - id: q
    sim:
      file: output.rch
      subbasin: 5
      variable: FLOW_OUT
      period: monthly
```

VIC：
```yaml
version: vic
driver: image
series:
  - id: runoff
    sim:
      variable: OUT_RUNOFF
      cell: [35, 42]
```

这个层次的目标是：
- 让用户面向模型概念配置
- 降低用户直接理解底层文件布局的成本

同时保留 `version: general` 作为专家模式，允许用户直接写 runtime 所需的底层 general config。

---

### 2. Discovery Layer

Discovery 的职责是：**识别项目事实**。

它只回答“这个项目实际上长什么样”，不负责做参数校准决策，也不负责做 I/O 执行。

#### Discovery 应负责的内容

- 模型版本
- driver 类型
- 项目目录结构
- 参数文件位置
- 输出文件位置
- 子流域 / HRU / 网格 / basin / station 等对象索引
- NetCDF 坐标变量 / mask 文件 / 栅格维度
- 输出时间尺度与文件命名规则

#### 示例

SWAT discovery：
- 找到所有 `.mgt` / `.hru` / `.sol` 文件
- 识别 subbasin / hru 编号关系
- 确认 `output.rch` / `output.hru` 的结构

VIC discovery：
- 识别 classic 还是 image driver
- 找到 global parameter file / params.nc / history.nc
- 提取 grid 维度、坐标变量、mask 信息

Noah-MP discovery：
- 找到 namelist、parameter table、forcing、restart、output 文件
- 确认输出变量所在文件和维度信息

---

### 3. Model Library Layer

Library 的职责是：**提供模型知识**。

它不扫描具体项目，而是维护该模型的一般性知识和默认规则。

#### Library 应负责的内容

- 参数定义
- 参数默认上下界
- 参数推荐 mode（`r` / `v` / `a`）
- 参数归属文件/变量类型
- 变量定义与映射
- 输出变量默认 readerType
- 典型 writerType / readerType 推荐
- 特定 driver 或模型版本的默认规则

#### 示例

SWAT library：
- `CN2` 属于 `.mgt`
- 推荐 mode 为 `r`
- `FLOW_OUT` 对应 `output.rch` 某列

VIC library：
- `infilt` 是参数变量
- Classic 下常见文本参数文件组织
- Image driver 下常见 NetCDF 参数变量与输出变量

Noah-MP library：
- `smcmax`、`bexp`、`psisat` 等参数定义
- 参数位于 table 还是 NetCDF
- 常见输出变量与维度说明

---

### 4. Template Builder / Config Expander Layer

这是整个“智能部署”框架的核心。

它负责把：

- 用户意图
- discovery 结果
- model library 知识

组合成统一的 **general config**。

#### Builder 应负责生成的内容

- `parameters.design`
- `parameters.physical`
- `writerType` 和对应的 writer spec
- `series[*].sim.readerType` 和对应的 reader spec
- functions / derived / objectives / diagnostics
- 必要时的 resolved general yaml

#### 一个典型例子

SWAT 用户写：
```yaml
version: swat
series:
  - id: q
    sim:
      file: output.rch
      subbasin: 5
      variable: FLOW_OUT
      period: monthly
```

Builder 可能展开成：
```yaml
series:
  - id: q
    sim:
      readerType: text
      file: output.rch
      rowRanges:
        - [220, 231]
      colNum: 7
```

VIC 用户写：
```yaml
version: vic
driver: image
series:
  - id: runoff
    sim:
      variable: OUT_RUNOFF
      cell: [35, 42]
```

Builder 可能展开成：
```yaml
series:
  - id: runoff
    sim:
      readerType: netcdf
      file: history.nc
      variable: OUT_RUNOFF
      selector:
        index:
          y: 35
          x: 42
```

Builder 的使命是：
- 把模型语言翻译成运行语言
- 不把这些模型知识泄漏到 runtime

---

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

## 九、模块职责建议

### 1. Template System

建议继续放在：
- `hydro_pilot/templates/<model_name>/`

每个模型模板目录推荐形成以下职责分工：

- `discovery.py`
- `library.py`
- `builder.py`
- `template.py`
- 必要时的 `variables.py`

### 2. Writers

建议继续放在：
- `hydro_pilot/params/writers/`

并补 registry 组织方式。

### 3. Readers

建议继续放在：
- `hydro_pilot/series/readers/`

并补 registry 组织方式。

### 4. Config

建议在：
- `hydro_pilot/config/specs.py`

中逐步补齐：
- `writerType`
- `readerType`
- 不同 type 对应的最小 spec 结构

---

## 十、与现有代码的衔接方式

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

### 因此推荐的第一批改造重点

1. 在不改变主行为的前提下完成 registry 化
2. 在 config 中明确 type 字段
3. 把 SWAT 模板整理成标准模板样板
4. 补 1~2 个高复用 I/O 能力作为验证

---

## 十一、后续模型接入的战略顺序

从框架成熟度和实现成本看，推荐顺序如下：

### 第一梯队：文本型 / 低门槛扩展
- SWAT（继续打磨）
- SWAT+
- APEX（若其主路径为文本表格/块状文本）
- VIC Classic
- XAJ lumped

### 第二梯队：多维科学数据型扩展
- VIC Image
- Noah-MP
- XAJ distributed

原因是：
- 第一梯队主要依赖文本型 reader/writer 能力扩展
- 第二梯队依赖 NetCDF / NPY / 栅格等更复杂基础设施

---

## 十二、主设计结论

hydroPilot 后续的模型智能部署框架应明确采用以下主思路：

> **用户面向模型语义写配置；系统通过 Discovery 获取项目事实，通过 Model Library 提供模型知识，再由 Template Builder 将用户语义展开为 General Config；运行时只消费 General Config，通过 Transformer、WriterRegistry、Runner、ReaderRegistry、Evaluator 和 Reporter 完成执行。**

这个结论意味着：

1. 未来的重点不是让 runtime 变得越来越懂模型
2. 而是让模板阶段承担足够的语义翻译职责
3. 同时让 runtime 保持稳定、通用、可扩展

这将成为 hydroPilot 架构演进的总定调。

---

## 十三、建议的下一步落地计划

### Phase 1：定边界
- 明确主链路采用 `Discovery -> Library -> Builder -> General Config -> Runtime`
- 明确 registry 只做格式分发
- 明确 general config 是唯一运行时协议

### Phase 2：做最小骨架
- writer registry 化
- reader registry 化
- config type 字段显式化
- SWAT 模板按 discovery/library/builder 拆清

### Phase 3：做第一批通用能力
- `KeyValueWriter`
- `DelimitedTableWriter`
- `TableReader`

### Phase 4：补 NetCDF 能力
- `NetCDFWriter`
- `NetCDFReader`
- selector spec 最小集

### Phase 5：逐步扩模型
- 先文本型模型
- 再多维科学数据模型

---

## 参考与相关文档

- `.claude/plans/mainstream_model_io_review.md`
- `.claude/plans/reporting-storage-review.md`
- 当前代码中的 SWAT 模板实现：
  - `hydro_pilot/templates/swat/template.py`
  - `hydro_pilot/templates/swat/discovery.py`
  - `hydro_pilot/templates/swat/library.py`
  - `hydro_pilot/templates/swat/builder.py`
