# hydroPilot 第一阶段开发计划（dev_plan1）

## Context

本计划文件用于承接 `architecture.md` 的主设计定调，目标不是一次完成全部模型智能部署框架，而是先落地第一阶段的“最小可生长骨架”。

第一阶段的核心任务是：

1. 不破坏现有主流程
2. 把 writer / reader 从单实现绑定改成可扩展入口
3. 把模板阶段的 `discovery / library / builder` 职责边界明确化
4. 为后续 `KeyValueWriter`、`DelimitedTableWriter`、`TableReader`、`NetCDFWriter/Reader` 预留结构空间

本阶段不追求一次支持多个新模型，而追求：

> 先让框架具备“长”的能力，再让模型一个个接进来。

---

## 一、阶段目标

### 目标 1：明确运行时协议边界

让 `general config` 真正成为 runtime 的唯一协议，至少在参数写入和结果提取层面显式体现：

- `writerType`
- `readerType`

### 目标 2：完成最小 registry 化

让：
- `ParamManager` 不再事实写死 `FixedWidthWriter`
- `SeriesExtractor` 不再事实写死 `TextReader`

即使当前仍只有一个实现，也要先把分发骨架补出来。

### 目标 3：整理 SWAT 模板为标准样板

不是继续只把 SWAT 当特例，而是把现有 SWAT 模板正式整理为：

- discovery
- library
- builder

三分法样板，用来指导未来新模型接入。

> 目标 3 的子方案见：[goal3_swat_template_plan.md](goal3_swat_template_plan.md)

### 目标 4：补第一批高复用 I/O 能力

在 registry 化完成后，优先补最通用、最容易验证价值的能力：

- `KeyValueWriter`
- `DelimitedTableWriter`
- `TableReader`

---

## 二、本阶段不做的事

为避免范围失控，以下内容明确不在 dev_plan1 中完成：

- 不搭建完整 integration framework
- 不做复杂 execution profile 体系
- 不做复杂 aggregation DSL
- 不一次支持 VIC / Noah-MP / XAJ distributed
- 不做完整 NetCDF selector 体系
- 不重写 `SimModel` 主流程
- 不重做 reporter 存储体系

这些内容保留到后续阶段。

---

## 三、第一阶段建议改动范围

### 1. Config 层

**目标**
- 让 `general config` 显式表达 I/O 类型。

**涉及文件**
- `hydro_pilot/config/specs.py`

**建议动作**
- 在参数物理项中引入 `writerType`
- 在 series 的 sim/obs 读取项中引入 `readerType`
- 保持现有 general config 尽量兼容；若用户未显式填写，可先给默认值：
  - writerType 默认 `fixed_width`
  - readerType 默认 `text`

**结果**
- runtime 不再靠隐式假设决定读写实现
- 模板生成 general config 时有明确落点

---

### 2. WriterRegistry

**目标**
- 把 writer 的选择逻辑从 `ParamManager` 中抽出，形成最小 registry。

**涉及文件**
- `hydro_pilot/params/writers/base.py`
- `hydro_pilot/params/writers/__init__.py`
- `hydro_pilot/params/manager.py`

**建议动作**
- 在 writers 包中建立 registry
- 初始注册：
  - `fixed_width -> FixedWidthWriter`
- 在 `ParamManager` 中，根据 `writerType` 获取 writer 实现
- 保持当前行为不变：若仍然全部走 `fixed_width`，结果应与现状一致

**完成标准**
- 不再直接在 manager 中硬编码创建 `FixedWidthWriter`
- 后续新增 writer 不需要改主分发逻辑

---

### 3. ReaderRegistry

**目标**
- 把 reader 的选择逻辑从 `SeriesExtractor` 中抽出，形成最小 registry。

**涉及文件**
- `hydro_pilot/series/readers/base.py`
- `hydro_pilot/series/readers/__init__.py`
- `hydro_pilot/series/extractor.py`

**建议动作**
- 在 readers 包中建立 registry
- 初始注册：
  - `text -> TextReader`
- 在 `SeriesExtractor` 中，根据 `readerType` 获取 reader 实现
- 保持当前文本提取逻辑兼容现有配置与测试

**完成标准**
- `SeriesExtractor` 不再事实绑定单一文本 reader
- 后续新增 `TableReader` / `NetCDFReader` 有明确扩展口

---

### 4. SWAT 模板样板化

**目标**
- 把 SWAT 从“当前唯一模板”整理成“未来模板规范样板”。

**涉及文件**
- `hydro_pilot/templates/swat/discovery.py`
- `hydro_pilot/templates/swat/library.py`
- `hydro_pilot/templates/swat/builder.py`
- `hydro_pilot/templates/swat/template.py`
- `hydro_pilot/templates/base.py`

**建议动作**
- 明确 discovery 只负责发现事实
- 明确 library 只负责参数/变量知识
- 明确 builder 只负责拼装 general config
- 在 template/base 中明确模板接口：
  - 如何 discover
  - 如何 build_config
  - 如何组织 library 依赖

**完成标准**
- SWAT 模板不再只是可用实现，而是可复用模式
- 新模型模板（如 VIC / APEX）后续可按同一骨架接入

---

## 四、第一批通用 I/O 能力

### 1. KeyValueWriter

**优先级：高**

**原因**
- 覆盖面广
- 适合大量配置型文件
- 实现复杂度低于 NetCDF

**适用场景**
- VIC global parameter file
- Noah-MP/陆面模型配置文件
- 一部分 XAJ 配置型文件

**建议能力边界**
- 支持 `key = value`
- 支持空格/等号分隔的简单 key-value 行
- 不一开始处理过于复杂的嵌套语法

---

### 2. DelimitedTableWriter

**优先级：高**

**原因**
- 是 SWAT+ / APEX / VIC Classic / 多种模型文本表格场景的共通能力

**适用场景**
- 分隔符表格
- 按列或按键定位的参数表

**建议能力边界**
- 支持 delimiter 指定
- 支持按行键/列名定位
- 第一阶段先支持最基本单元格修改，不做复杂联动更新

---

### 3. TableReader

**优先级：高**

**原因**
- 是当前 `TextReader` 向更通用文本输出读取演进的自然方向

**适用场景**
- CSV / 空格分隔表格
- 带 header 的结构化文本输出
- SWAT+ / APEX / VIC Classic 的部分输出

**建议能力边界**
- 支持 delimiter
- 支持 header
- 支持按列名读取
- 支持 skip rows
- 第一阶段不做复杂多 section 解析

---

## 五、实现顺序建议

### Step 1：Config 显式化
先补 `writerType` / `readerType`，建立 general config 的新边界。

### Step 2：registry 化
先完成 writer / reader 的最小 registry 改造，但只挂接现有实现。

### Step 3：SWAT 模板规范化
用 SWAT 模板验证 discovery / library / builder 的职责边界。

### Step 4：补第一批 I/O 能力
先做：
- `KeyValueWriter`
- `DelimitedTableWriter`
- `TableReader`

### Step 5：验证端到端兼容性
确保现有 SWAT/general 工作流不被破坏，再考虑 Phase 2 的 NetCDF。

---

## 六、验证策略

### 1. 回归验证
- 现有示例配置仍可运行
- 现有 SWAT 路径行为不变
- `pytest` 基线通过

### 2. 结构验证
- `writerType` 改变后，运行时确实通过 registry 分发
- `readerType` 改变后，运行时确实通过 registry 分发

### 3. 样例验证
- 至少提供一个 `KeyValueWriter` 样例
- 至少提供一个 `DelimitedTableWriter` 样例
- 至少提供一个 `TableReader` 样例

### 4. 模板验证
- 模板展开出的 `_general.yaml` 可独立运行
- runtime 不需要知道模板模型名

---

## 七、完成后的阶段成果

当 dev_plan1 完成后，系统应具备以下新能力：

1. runtime 已明确支持 `writerType` / `readerType`
2. writer / reader 已具备最小注册式扩展能力
3. SWAT 模板已成为未来模型接入的样板
4. 文本型表格 / key-value I/O 的扩展通道已经打通
5. 后续进入 NetCDF 阶段时，不需要重做主链路

---

## 八、下一阶段衔接

dev_plan1 完成后，可进入第二阶段，重点是：

- `NetCDFWriter`
- `NetCDFReader`
- selector spec 最小集
- 以 VIC Image / Noah-MP 为目标验证 NetCDF 路线

也就是说，dev_plan1 的任务不是“完成最终框架”，而是：

> 把 hydroPilot 从“单一实现可用”推进到“通用框架开始成型”。
