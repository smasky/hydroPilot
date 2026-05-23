# SWAT+ 流量抽取指南

如何使用 hydroPilot 的 `version: swatplus` 模板从 SWAT+ 输出文件中抽取径流时间序列。本文覆盖三条主路线，并解释模板如何将 `variable` + `id` + `period` 自动解析为具体的列位置和行范围。

## 快速参考：我应该用哪个文件？

| 你想取什么 | 文件 | 变量名 | `id` 含义 | 可用条件 |
|-----------|------|--------|----------|----------|
| 流域出口产水量 | `basin_wb_*.txt` | `WYLD` | 固定为 `1` | 总是可用 |
| HRU 产水量 | `hru_wb_*.txt` | `WYLD` | HRU 编号 | 总是可用 |
| 水文站出流量 | `hydout_*.txt` | `FLOW_OUT` | hydrology 对象编号 | 项目中需有 hydrology 对象 |
| 水文站入流量 | `hydin_*.txt` | `FLOW_IN` | hydrology 对象编号 | 项目中需有 hydrology 对象 |
| 河道断面出流量 | `channel_sd_*.txt` | `flo_out` | reach 编号 | 项目中需有 channel 对象 |

## 路线一：流域出口产水量

最常用的路线。取整个流域出口的总产水量（水深 mm）。对应 SWAT 2012 的 `output.sub` + `WYLD`。

**系列库已注册的变量**：`PREC`（降水）、`ET`（蒸散发）、`WYLD`（产水量）、`PERC`（深层渗漏）、`SURQ`（地表径流）

**频率选择**：

| 频率 | 文件名 | 每年数据行数 | 适用场景 |
|------|--------|-------------|----------|
| 年均 (`aa`) | `basin_wb_aa.txt` | 1 | 年尺度水量平衡 |
| 逐年 (`yr`) | `basin_wb_yr.txt` | 1 | 逐年校验 |
| 逐月 (`mo`) | `basin_wb_mo.txt` | 12 | 月尺度率定 |
| 逐日 (`da`) | `basin_wb_da.txt` | 365 | 日尺度率定 |

**示例 — 月尺度**：

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

- `variable: WYLD` — 模板自动从系列数据库中查找列位置。
- `id: 1` — basin 对象固定为 1（每个项目只有一个 basin）。
- `period: [2010, 2020]` — 抽取 2010 到 2020 年（含首尾）。模板根据项目元数据自动计算行号范围。
- 产水量单位是 mm，如需转为 m³/s，需在 derived 层用流域面积做换算。

**不需要手工写 `colSpan` 或 `rowRanges`。** 模板会从系列数据库和工程发现信息中自动解析。

## 路线二：水文站出流量

取特定 hydrology 对象（相当于水文站断面）的出流量（m³/s）。对应 SWAT 2012 的 `output.rch` + `FLOW_OUT`。

**系列库已注册的变量**：`FLOW_OUT`（出流量）、`FLOW_IN`（入流量）

**频率选择**：

| 频率 | 文件名 | 每年数据行数 |
|------|--------|-------------|
| 年均 (`aa`) | `hydout_aa.txt` | 1 |
| 逐年 (`yr`) | `hydout_yr.txt` | 1 |
| 逐月 (`mo`) | `hydout_mo.txt` | 12 |
| 逐日 (`da`) | `hydout_da.txt` | 365 |

**示例 — 日尺度**：

```yaml
series:
  - id: flow_at_gauge
    sim:
      file: hydout_da.txt
      variable: FLOW_OUT
      id: 1
      period: [2018, 2020]
    obs:
      file: obs_flow_daily.txt
      rowRanges: [[1, 1095]]
      colNum: 1
```

- `hydout_*.txt` 的单位已经是 m³/s，无需面积换算——这是与路线一的关键区别。
- `id` 是 hydrology 对象编号，对应 `hru-data.hru` 中 `hydro_name` 列的数字后缀（如 `hyd0001` → id=1）。

**如何找到正确的 id**：

1. 打开项目的 `hydrology.hyd` 文件，第一列 (`name`) 列出了所有 hydrology 对象名，如 `hyd0001`, `hyd0002`。
2. `id` = 名字中 `hyd` 后面的数字：`hyd0003` → `id: 3`。
3. 也可以通过 `hru-data.hru` 的 `hydro_name` 列反查：它告诉你每个 HRU 的水流向哪个 hydrology 对象。

## 路线三：河道断面出流量

取特定河道断面的出流量。对应 SWAT 2012 的 `output.rch` + `FLOW_OUT`（per-reach）。

**重要约束**：此路线需要项目中存在 channel 对象。没有 routing 的项目（如 Ames_sub1 的 `object.cnt` 中 channel count = 0）不能使用此路线。

**channel 输出中的变量**：`flo_out`（出流量）、`flo_in`（入流量）、`evap`（蒸发）、`tlost`（传输损失）、`sed_out`（出沙量）

**示例 — 月尺度**：

```yaml
series:
  - id: reach_flow
    sim:
      file: channel_sd_mo.txt
      variable: flo_out
      id: 3
      period: [2010, 2020]
    obs:
      file: obs_reach_flow.txt
      rowRanges: [[1, 132]]
      colNum: 1
```

- `id` 是 reach 编号（从 1 开始），对应 `channel-lte.cha` 中的行顺序。
- channel 输出的变量名与 basin/hru 输出不同（如 `flo` 而非 `FLOW_OUT`）。务必使用系列数据库中注册的准确变量名。

## SWAT 2012 → SWAT+ 对照表

| SWAT 2012 | SWAT+ | 说明 |
|-----------|-------|------|
| `file: output.rch` + `FLOW_OUT` + `id: 33` | `file: hydout_*.txt` + `FLOW_OUT` + `id: <hyd_obj>` | 河段流量 → hydrology 对象流量 |
| `file: output.sub` + `WYLD` + `id: N` | `file: basin_wb_*.txt` + `WYLD` + `id: 1` | 子流域产水 → 流域产水 |
| `file: output.hru` + `WYLD` | `file: hru_wb_*.txt` + `WYLD` | HRU 产水量 |
| `period: [2010, 2015]` | `period: [2010, 2015]` | 写法相同 |

与 SWAT 2012 的关键差异：

- SWAT 2012 的 `output.rch` 在 SWAT+ 中被拆分为 `hydout_*`（hydrology 对象）和 `channel_sd_*`（channel 对象）。
- SWAT 2012 的 reach id 不能直接套用到 SWAT+——需要对照项目的 `hydrology.hyd` 或 `channel-lte.cha` 确认编号。
- `basin_wb_*` 流域输出始终可用，不依赖 routing 配置。

## 配置速查清单

按以下顺序确认 series 配置即可：

1. **确定空间位置**
   - 流域出口 → `basin_wb_*.txt` + `WYLD` + `id: 1`
   - 水文站 → `hydout_*.txt` + `FLOW_OUT` + `id: <hyd_id>`
   - 河道断面 → `channel_sd_*.txt` + `flo_out` + `id: <reach_id>`

2. **确定时间分辨率**
   - 年尺度 → `_aa.txt` 或 `_yr.txt`
   - 月尺度 → `_mo.txt`
   - 日尺度 → `_da.txt`

3. **确定时间范围**
   - `period: [起始年, 结束年]` — 包含首尾两年

4. **定义观测数据**
   - `obs.file` — 观测文件路径（相对配置文件所在目录）
   - `obs.colNum` 或 `obs.colSpan` — 观测值的列位置

5. **验证空间 ID**
   - 模板会检查 `id` 是否在 `[1, 对象总数]` 范围内。超出范围的 id 会抛出明确的 `ValueError`。

## 模板自动解析了什么

你只需要写：

```yaml
sim:
  file: basin_wb_mo.txt
  variable: WYLD
  id: 1
  period: [2010, 2020]
```

模板会自动完成：

- `colSpan` — 从 `swatplus_db.yaml` 中按输出文件名和变量名查找列位置。
- `rowRanges` — 根据项目元数据（起始年、结束年、输出频率、对象数量、表头行数）计算行号范围。
- `readerType` — 设为 `text`（SWAT+ 输出文件使用定宽文本格式）。

展开后的 `_general.yaml` 配置会包含解析后的 `colSpan` 和 `rowRanges`，可以通过查看该文件来验证解析结果。

## 注意事项

- **obs 需要显式列位置**：`sim` 侧可以用 `variable` 简化，但 `obs` 侧的 `colNum` / `colSpan` 必须明确给出（obs 文件不是 SWAT+ 输出，系列库中没有其布局信息）。
- **频率文件必须实际存在**：系列库补齐了所有频率的条目，但如果项目的 `print.prt` 未启用对应频率输出（如 Ames_sub1 只有 `avann=y`），则 yr/mo/da 的实际输出文件不存在。配置可以正确解析，但运行时读取需要实际文件。
- **period 使用年份**：period 按年份解析（取 `-` 前的部分），与 SWAT 2012 的行为一致。

## 参见

- [SWAT+ 模板](../templates/swatplus.md) — `version: swatplus` 完整模板参考。
- [SWAT 2012 模板](../templates/swat-2012.md) — SWAT 2012 对应文档。
- [配置参考](../configuration-reference.md) — 所有 general 模式字段说明。
