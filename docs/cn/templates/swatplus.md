# SWAT+ 模板

`version: swatplus` 是面向 **SWAT+**（SWAT Plus）工程的模板。你只需声明参数名和取值范围，模板就会生成面向 `calibration.cal` 的参数修改记录。hydroPilot 会在运行前把模板展开为标准 `version: general` 配置。

## 模板展开后是什么

| 方面 | 模板输入 | 展开后的 general 输出 |
|---|---|---|
| Writer 类型 | 隐式 | `writerType: formatted_text` |
| Reader 类型 | 隐式 | `readerType: text` |
| 参数位置 | 变量名 + mode + 可选 filter | `calibration.cal` 中的标定记录（`row`/`col`/`width`） |
| 序列行定位 | `id` + `period` | 计算出的 `rowRanges` |
| 序列列定位 | `variable` 名称 | 从 SWAT+ 系列数据库解析出的 `colSpan` |

模板展开由 `SwatPlusTemplate.build_config()` 完成。所有参数写入目标统一为 `calibration.cal` 文件——模板在实例初始化时生成骨架（表头 + 占位记录），运行时将率定值写入 `VAL` 列。

## 配置结构

### `version`

```yaml
version: swatplus
```

### `basic`

```yaml
basic:
  projectPath: ./Ames_sub1/TxtInOut
  workPath: ./work
  command: swatplus.exe
```

### `parameters`

两层设计：

- `design` — 优化器可见的变量（name、bounds、可选 type、可选 mode）。
- `physical` — 变量如何写入。模板生成 `calibration.cal` 记录（SWAT+ 参数变更格式）。`mode` 字段映射到 `CHG_TYPE`：`v` → `absval`，`a` → `abschg`，`r` → `pctchg`。省略时从 SWAT+ 参数数据库自动填充默认值。

```yaml
parameters:
  design:
    - name: surq_lag
      bounds: [0.05, 24.0]
    - name: esco
      bounds: [0.0, 1.0]

  physical:
    - name: surq_lag
      mode: v
    - name: esco
      mode: v
```

#### 参数过滤

限定参数作用的空间对象。模板根据项目元数据解析 filter 规格，将匹配的对象 ID 写入 `calibration.cal` 记录的对象 ID 尾部（`OBJ_TOT` + 右对齐的 ID 列表）。

**支持矩阵：**

| 组 | 文件 | 对象类型 | 支持的 filter 键 | 备注 |
|----|------|----------|-----------------|------|
| A | `parameters.bsn` | basin（全局） | 无 | OBJ_TOT=0——全局参数，filter 会被校验拒绝 |
| B | `hydrology.hyd` | HRU | `object_id`、`lu_mgt`、`soil`、`hydro_name` | 通过 `hru-data.hru` 元数据解析 |
| C | `hyd-sed-lte.cha` | channel reach | `object_id`（仅此一种） | Reach ID = `channel-lte.cha` 中的顺序行号 |
| D | `soils.sol` | soil 选择器，率定对象空间仍为 HRU | `soil` | 用户写 soil 名称，最终写入的 calibration object IDs 仍是 HRU IDs |

过滤规则：同一键内的列表值为 OR，不同键为 AND。

```yaml
physical:
  - name: esco
    mode: v
    filter:
      lu_mgt: cosy_lum          # B 组——HRU 过滤
  - name: ch_mann
    mode: v
    filter:
      object_id: [1, 3, 5]      # C 组——channel reach ID
  - name: sol_bd
    mode: v
    filter:
      soil: soil_01             # D 组——土壤名称入口，最终解析为 HRU IDs
```

**当前 filter 边界：**

- 原生标定条件语法（`cal_group`、`hsg`、texture、plant class 等）尚未实现——filter 始终转换为对象 ID。
- `soils.sol` 在 SWAT+ calibration 中的对象空间是 HRU。soil/profile 名称只用于找出命中的 HRUs。
- soils.sol 的 filter 使用精确土壤名称匹配。带水文后缀的变体（如 `soil_01-h1`）不会匹配其基础名称（`soil_01`）——请使用 `hru-data.hru` 中的完整名称。
- channel filter 仅支持 `object_id` 透传。基于属性的 channel selector（name、order）尚未实现。
- 土层级定位（selectIndex、LYR1/LYR2）尚未实现——土壤参数变更会应用到匹配剖面所有土层。
- 非 HRU 对象（aquifer、reservoir）的 filter 定位尚未支持。

### `series`

SWAT+ 系列描述如何从 SWAT+ 文本输出文件中抽取模拟结果。

```yaml
series:
  - id: flow
    sim:
      file: basin_wb_mo.txt
      variable: WYLD
      id: 1
      period: [2010, 2020]
    obs:
      file: obs_flow_monthly.txt
      rowRanges: [[1, 132]]
      colNum: 1
```

使用 `variable` 时，模板从 SWAT+ 系列数据库（`swatplus_db.yaml`）中查找列位置。

### `functions`、`derived`、`objectives`

与 general 模式结构相同。

## 项目发现

模板读取 SWAT+ 项目目录以提取元数据：

| 文件 | 读取内容 |
|------|----------|
| `file.cio` | 文件映射（time.sim、print.prt、hru-data.hru 等） |
| `time.sim` | 模拟起止年份、步长 |
| `print.prt` | 输出间隔（月/日/年）、nyskip |
| `hru-data.hru` | HRU 数量、HRU 属性（lu_mgt、soil、hydro_name） |
| `channel-lte.cha` | `hyd-sed-lte.cha` 的 reach 数量，用于 `object_id` 范围校验 |

这些元数据用于：计算 series 的 rowRanges 和验证空间 ID 范围。

## 参数数据库

SWAT+ 参数数据库（`swatplus_db.yaml`）提供参数名称、类型和取值范围，用于验证和默认值填充。当前覆盖四组文件：

| 组 | 文件 | 参数数量 | 状态 |
|----|------|----------|------|
| A | `parameters.bsn` | 26 | 全局（basin）；无 filter |
| B | `hydrology.hyd` | 14 | HRU filter：`object_id`、`lu_mgt`、`soil`、`hydro_name` |
| C | `hyd-sed-lte.cha` | 6 | Channel filter：`object_id`（reach ID 来自 `channel-lte.cha`） |
| D | `soils.sol` | 8 | soil 名称选择器；最终率定对象 ID 仍为 HRU IDs |

所有设计参数均写入统一的 `calibration.cal` 文件（通过 `formatted_text` 记录）。数据库中各参数文件的列位置信息保留供向前兼容，但当前 writer 路径不再直接使用。

## 系列数据库

SWAT+ 系列数据库已覆盖 Tier 1 流量抽取所需的全部标准频率文件：`hydout`、`hydin`、`basin_wb`、`channel_sd` 均支持 `aa`（年均）、`yr`（逐年）、`mo`（逐月）、`da`（逐日）四种频率。其他报告类型在非 `aa` 频率下的补库工作已列入后续计划。

## 参见

- [SWAT+ 流量抽取指南](../guides/swatplus-flow-extraction.md) — 如何从 SWAT+ 输出文件中抽取径流。
- [SWAT 2012 模板](swat-2012.md) — SWAT 2012 对应文档。
- [配置参考](../configuration-reference.md) — 所有 general 模式字段说明。
