# 主流水文模型 I/O 适配规划：SWAT、APEX、VIC、XAJ、Noah-MP

## Context

用户希望从参数写入层、数据读出层、模板配套三个角度，审视 hydroPilot 后续要支持 SWAT、APEX、VIC、XAJ、Noah-MP 这些主流水文/陆面模型时，还需要补哪些能力。

当前 hydroPilot 已经具备一条通用主链路：配置加载 → 参数写入 → 模型执行 → 结果提取 → 指标评估 → 结果记录。但从代码现状看，I/O 适配能力仍以 SWAT 传统文本场景为核心：

- 参数写入主要依赖 `FixedWidthWriter`
- 数据读出主要依赖 `TextReader`
- 模板层目前 SWAT 最完整
- runner 当前主要是本地 `SubprocessRunner`

因此，下一步规划不应只问“能不能跑某个模型”，而应拆成三个层面：

1. 这个模型的参数主要存在哪里、以什么格式组织
2. 这个模型的输出主要是什么格式、是否需要按空间/时间维度提取
3. 是否需要模型模板帮助用户从简化配置展开到 general 配置

## 总体判断

如果只覆盖传统 SWAT/SWAT-like 文本文件，当前框架已经有基础。但如果要覆盖 VIC、Noah-MP、分布式 XAJ 这类 NetCDF / NPY / 栅格 / 多维数组工作流，则 hydroPilot 还需要显著增强：

- 参数写入层需要从 fixed-width 扩展到 key-value、表格、YAML/JSON、NetCDF、多文件参数集
- 数据读出层需要从 line/column 文本提取扩展到 NetCDF、NPY、CSV、栅格、时间维/空间维选择
- 模板层需要承担模型发现、参数库、默认输出变量、空间对象索引映射、driver 类型识别等工作

## 模型逐项审视

### 1. SWAT

#### 当前适配基础

SWAT 是当前项目里基础最好的模型方向。已有：

- `hydro_pilot/templates/swat/template.py`
- `hydro_pilot/templates/swat/discovery.py`
- `hydro_pilot/templates/swat/library.py`
- `hydro_pilot/templates/swat/builder.py`
- `hydro_pilot/templates/swat/variables.py`
- `FixedWidthWriter`
- `TextReader`

当前能力更接近传统 SWAT/SWAT2012 的文本输入输出工作流。

#### 参数写入还需要做什么

短期：
- 继续完善 SWAT 参数库覆盖范围
- 固化 `.mgt`、`.gw`、`.hru`、`.sol`、`.rte` 等常见参数文件的写入测试
- 对同一参数写多个文件、多行、多对象的场景补测试
- 明确相对变化 `r`、替换 `v`、加法 `a` 在 SWAT 参数上的边界

中期：
- 区分 SWAT2012 与 SWAT+ 的 I/O 差异
- SWAT+ 输入文件偏 free-format / space-delimited，不能全部假设为固定宽度
- 需要增加 `DelimitedTableWriter` 或 `KeyValueTableWriter`，用于处理 SWAT+ 风格表格型输入

#### 数据读出还需要做什么

短期：
- 继续完善 `output.rch`、`output.sub`、`output.hru` 的行列定位逻辑
- 对日尺度、月尺度、年尺度输出分别建立测试
- 对不同 subbasin / hru / variable 的行号计算建立稳定单测

中期：
- SWAT+ 输出可能涉及新的文本表格或 SQLite/结构化输出场景
- 需要比当前 `TextReader` 更强的 header-aware table reader
- 需要支持按列名读取，而不是只靠固定行列位置

#### 模板配套还需要做什么

- 把 SWAT 模板继续作为“样板间”打磨
- 明确 SWAT2012 与 SWAT+ 是一个模板内分支，还是拆成两个模板
- 增强 project discovery：识别模型版本、输出时间尺度、subbasin/hru 索引
- 保持模板展开后仍落到 general 配置，不让 SimModel 感知 SWAT 特殊逻辑

### 2. APEX

#### 适配难点

APEX 与 SWAT 一样有较强的农业水文模型背景，文件形态上大概率仍有大量文本参数文件和输出文件。但相比 SWAT，当前仓库没有 APEX 参数库、项目发现、输出变量定位等基础设施。

#### 参数写入需要做什么

短期：
- 先建立 APEX 参数文件清单和参数库
- 确认主要参数文件是固定宽度、定界文本、还是 key-value 风格
- 如果与 SWAT 类似，可复用 `FixedWidthWriter`
- 如果是定界表格或块状文本，需要新增表格/块状 writer

建议优先补：
- `DelimitedTableWriter`
- `BlockTextWriter`
- 参数库结构：参数名、文件、行/字段定位、上下界、默认变换模式

#### 数据读出需要做什么

短期：
- 梳理 APEX 常见输出文件及变量位置
- 如果输出是按列文本表，可复用增强后的 table reader
- 如果输出文件包含多个 section，需要 reader 支持 section 定位

需要重点关注：
- 日尺度/月尺度输出
- 流量、泥沙、养分、作物相关变量
- 多子流域/管理单元输出的索引方式

#### 模板配套需要做什么

APEX 至少需要：
- project discovery：识别项目文件结构和主要控制文件
- parameter library：常用校准参数库
- variable resolver：把用户指定的变量/空间单元/时间尺度翻译成 reader spec
- builder：从简化配置展开到 general config

APEX 不建议一开始就做完整模板，应先选一套典型项目结构做最小闭环。

### 3. VIC

#### 适配难点

VIC 是 hydroPilot 当前能力缺口最大的方向之一，因为 VIC 有 Classic Driver 与 Image Driver 两类常见工作流：

- Classic Driver 偏 ASCII 文本输入输出
- Image Driver 偏 NetCDF 输入输出

这意味着 VIC 不能只靠 `FixedWidthWriter + TextReader` 覆盖。

#### 参数写入需要做什么

Classic Driver：
- 需要支持 global parameter file 的 key-value 修改
- 需要支持 soil parameter file、vegetation library、vegetation parameter 等文本表格修改
- 需要 `KeyValueWriter` 和 `DelimitedTableWriter`

Image Driver：
- 需要支持 NetCDF 参数文件修改
- 需要按变量名、维度、坐标或 mask 选择写入区域
- 需要 `NetCDFWriter`

建议新增 writer：
- `KeyValueWriter`：修改 global parameter file 这类配置项
- `DelimitedTableWriter`：修改 soil/veg 等 ASCII 参数表
- `NetCDFWriter`：修改 NetCDF 参数变量

#### 数据读出需要做什么

Classic Driver：
- 支持 ASCII output 的按文件、按列名、按时间步读取
- 当前 `TextReader` 可作为基础，但需要 header-aware 能力

Image Driver：
- 必须支持 NetCDF 读取
- 需要按 variable、time、lat/lon 或 grid index、basin mask 聚合读取
- 需要支持输出频率、历史文件、多文件拼接

建议新增 reader：
- `TableReader`：面向有 header 的 ASCII 表格
- `NetCDFReader`：面向变量名和多维坐标读取
- 可选 `SpatialAggregateReader`：在 NetCDFReader 之上做区域平均/汇总

#### 模板配套需要做什么

VIC 模板应首先识别 driver 类型：
- classic
- image

然后分别展开：
- 输入文件位置
- 参数文件类型
- 输出变量映射
- 空间维度信息

VIC 模板的关键不是参数库本身，而是 driver 类型和文件组织方式识别。

### 4. XAJ

#### 适配难点

XAJ/新安江模型的工程实现差异非常大：有传统集总式实现，也有分布式实现。不同团队的文件格式可能完全不同。

从公开资料看，传统 XAJ 常见输入是面雨量、蒸发，输出是流量；分布式 XAJ 变体可能使用 YAML 配置、NPY 数组、Esri ASCII 栅格、CSV/XLSX 查找表，并输出 NPY 状态变量和通量。

因此 XAJ 不应一开始假设存在统一标准文件格式。

#### 参数写入需要做什么

传统集总式 XAJ：
- 很多实现可能把参数放在 YAML、JSON、INI、CSV 或简单文本中
- 应优先支持 `YamlWriter`、`JsonWriter`、`KeyValueWriter`、`CsvTableWriter`

分布式 XAJ：
- 参数可能位于 YAML 配置、栅格、查找表或 NPY 数组中
- 需要支持数组/栅格类参数写入

建议新增 writer：
- `YamlWriter`
- `JsonWriter`
- `CsvTableWriter`
- `NpyWriter`
- 可选 `RasterAsciiWriter`

#### 数据读出需要做什么

传统集总式 XAJ：
- 输出多为流量时间序列，CSV/文本 reader 基本可覆盖

分布式 XAJ：
- 输出可能是 NPY 格式的状态变量和模型通量
- 栅格输入输出可能是 Esri ASCII
- 需要支持数组读取、时间维选择、空间聚合

建议新增 reader：
- `CsvReader` / 增强版 `TableReader`
- `NpyReader`
- `RasterAsciiReader`
- 可选空间聚合工具

#### 模板配套需要做什么

XAJ 模板最好不要一开始做成“大一统 XAJ 模板”。建议拆成：

- `xaj_lumped`：传统集总式模板
- `xaj_distributed`：分布式模板

模板层需要明确：
- 参数集合和单位
- 输入 forcing 格式
- 输出 discharge 的位置
- 是否存在空间网格或流域 mask

### 5. Noah-MP

#### 适配难点

Noah-MP 更接近陆面模式/陆面过程模型，常与 WRF-Hydro、HRLDAS 等系统结合。它的输入输出和参数形态通常更偏：

- namelist 配置
- parameter tables
- NetCDF forcing / restart / output
- 多维空间网格变量

因此 Noah-MP 对 hydroPilot 的要求更接近“多维科学数据 I/O 框架”，而不是传统文本行列读写。

#### 参数写入需要做什么

需要优先支持：
- namelist 文件修改
- 参数表修改
- NetCDF 参数或初始状态修改

建议新增 writer：
- `NamelistWriter`
- `KeyValueWriter`
- `DelimitedTableWriter`
- `NetCDFWriter`

Noah-MP 的参数写入还需要特别注意：
- 参数可能是全局表项，也可能是空间分布变量
- 参数可能与 land cover / soil type / vegetation type 等分类有关
- 同一个设计参数可能映射到多个空间单元或多个变量

#### 数据读出需要做什么

Noah-MP 输出通常需要：
- NetCDF 变量读取
- time 维度选择
- grid cell / basin mask / station 映射
- 多文件历史输出拼接
- restart/state 文件读取

因此 `NetCDFReader` 是 Noah-MP 支持的前置条件。

建议 reader 能力：
- 按变量名读取
- 按 time slice 读取
- 按空间索引或经纬度读取
- 按 mask 做区域平均/总量
- 支持多文件拼接

#### 模板配套需要做什么

Noah-MP 模板需要：
- 识别 namelist / parameter table / forcing / restart / output 文件路径
- 定义常见输出变量映射
- 定义常见参数表项映射
- 支持 HRLDAS / WRF-Hydro 场景差异

Noah-MP 不建议作为早期第一个新增模板，因为它会倒逼 NetCDF、多维空间聚合、namelist writer 等多个基础能力同时成熟。

## 横向能力缺口清单

### 参数写入层优先级

#### P0：短期最该补

1. `KeyValueWriter`
   - 适用：VIC global parameter、Noah-MP 配置项、部分 XAJ 配置
   - 价值：覆盖大量“参数名 = 值”类配置文件

2. `DelimitedTableWriter`
   - 适用：SWAT+、VIC soil/veg、APEX 表格参数、Noah-MP 参数表
   - 价值：比 fixed-width 更通用

3. writer 注册/分发机制
   - 当前不应继续把 fixed-width 作为事实唯一实现
   - 参数库或配置中应明确 writerType

#### P1：中期必须补

4. `YamlWriter` / `JsonWriter`
   - 适用：XAJ、现代 Python/科研模型配置

5. `NamelistWriter`
   - 适用：Noah-MP、WRF-Hydro/HRLDAS 类 Fortran 模型配置

6. `NetCDFWriter`
   - 适用：VIC Image Driver、Noah-MP、部分分布式模型

#### P2：按模型需求补

7. `NpyWriter`
   - 适用：分布式 XAJ / Python 科研模型

8. `RasterAsciiWriter`
   - 适用：分布式 XAJ、栅格型模型参数

### 数据读出层优先级

#### P0：短期最该补

1. `TableReader`
   - 支持 header、列名、delimiter、skip rows、section
   - 是当前 `TextReader` 的自然增强方向

2. reader 注册/分发机制
   - 不应让 `SeriesExtractor` 永远直接调用 `read_text_extract()`

#### P1：中期必须补

3. `NetCDFReader`
   - 适用：VIC Image Driver、Noah-MP
   - 是支持现代分布式/陆面模型的关键能力

4. `CsvReader` / `DataFrameReader`
   - 适用：XAJ、APEX、后处理输出

#### P2：按模型需求补

5. `NpyReader`
   - 适用：分布式 XAJ

6. `RasterAsciiReader`
   - 适用：分布式 XAJ、栅格结果

7. 空间聚合 reader/helper
   - 支持 grid → basin/station 的聚合
   - 对 VIC/Noah-MP/XAJ 分布式输出都重要

## 推荐实施顺序

### 阶段 1：先把 I/O 注册机制补上

**目标**
- 让 writerType / readerType 真正决定使用哪个实现。

**原因**
- 否则后续新增 writer/reader 会继续把逻辑塞进 manager/extractor，架构会变乱。

**涉及文件**
- `hydro_pilot/params/manager.py`
- `hydro_pilot/params/writers/base.py`
- `hydro_pilot/series/extractor.py`
- `hydro_pilot/series/readers/base.py`
- `hydro_pilot/config/specs.py`

### 阶段 2：补两个最通用文本能力

**目标**
- 在不引入复杂科学数据依赖前，先覆盖 SWAT+、APEX、VIC Classic、XAJ lumped 的大部分文本场景。

**建议实现**
- `KeyValueWriter`
- `DelimitedTableWriter`
- `TableReader`

### 阶段 3：补 NetCDF 能力

**目标**
- 打开 VIC Image Driver 和 Noah-MP 的适配可能性。

**建议实现**
- `NetCDFReader`
- `NetCDFWriter`
- 基础空间选择和时间选择能力

### 阶段 4：补数组/栅格能力

**目标**
- 支持分布式 XAJ 和其他 Python/栅格型水文模型。

**建议实现**
- `NpyReader` / `NpyWriter`
- `RasterAsciiReader` / `RasterAsciiWriter`
- 简单 basin mask 聚合能力

### 阶段 5：再扩具体模型模板

**建议顺序**

1. SWAT / SWAT+：继续打磨现有模板
2. VIC Classic：依赖 KeyValueWriter + TableReader
3. XAJ lumped：依赖 YAML/CSV/key-value 能力
4. APEX：依赖参数库整理和 table/block text reader-writer
5. VIC Image / Noah-MP / XAJ distributed：依赖 NetCDF/NPY/栅格能力成熟

## 推荐路线结论

短期不要直接说“支持五个模型”，而应先说：

- 第一阶段支持传统文本模型 I/O：SWAT、APEX、VIC Classic、XAJ lumped
- 第二阶段支持多维科学数据 I/O：VIC Image、Noah-MP、XAJ distributed

这样 hydroPilot 的扩展路径会更稳：先补通用 I/O 底座，再做模型模板，而不是每个模型写一套特殊逻辑。

## 参考来源

- [SWAT+ input file format](https://swatplus.gitbook.io/io-docs/introduction-1/input-file-format)
- [SWAT documentation hub](https://swat.tamu.edu/docs/)
- [SWAT 2012 I/O documentation PDF](https://swat.tamu.edu/media/69296/swat-io-documentation-2012.pdf)
- [VIC Image Driver output formatting](https://vic.readthedocs.io/en/master/Documentation/Drivers/Image/OutputFormatting/)
- [VIC Classic Driver output formatting](https://vic.readthedocs.io/en/master/Documentation/Drivers/Classic/OutputFormatting/)
- [VIC Image Driver inputs](https://vic.readthedocs.io/en/vic.5.0.0/Documentation/Drivers/Image/Inputs/)
- [VIC Classic Driver inputs](https://vic.readthedocs.io/en/master/Documentation/Drivers/Classic/Inputs/)
- [NCAR Noah-MP repository](https://github.com/NCAR/noahmp)
- [Noah-MP v5.0 GMD paper](https://gmd.copernicus.org/articles/16/5131/2023/gmd-16-5131-2023.html)
- [Noah-MP parameter table](https://ral.ucar.edu/sites/default/files/public/product-tool/noah-multiparameterization-land-surface-model-noah-mp-lsm/mptable.html)
- [WRF-Hydro technical description and user guide](https://ral.ucar.edu/sites/default/files/public/projects/wrf-hydro/technical-description-user-guide/wrf-hydrov5.2technicaldescription.pdf)
- [HESS 2025 TDD-XAJ article](https://hess.copernicus.org/articles/29/3745/2025/)
- [HESS 2025 TDD-XAJ PDF](https://hess.copernicus.org/articles/29/3745/2025/hess-29-3745-2025.pdf)
- [HESS 2017 XAJ-EB article](https://hess.copernicus.org/articles/21/3359/2017/)
