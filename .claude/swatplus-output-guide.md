# SWAT+ Output Guide

这份文档只回答一个问题：

- `SWAT+` 的 output 到底是怎么组织的
- 如果你习惯了 `SWAT2012` 的 `output.rch / output.sub / output.hru`
- 那么到了 `SWAT+`，应该怎么理解它的输出体系

---

## 1. 先说结论

`SWAT2012` 的输出组织方式更像：

- 少数几个大文件
- 每个文件里靠列和对象 id 区分内容

而 `SWAT+` 的输出组织方式更像：

- 先按 **对象类型**
- 再按 **报告类型**
- 再按 **时间频率**
- 拆成很多个独立文本文件

它的主命名模式是：

```text
{object}_{report}_{frequency}.txt
```

例如：

- `basin_wb_aa.txt`
- `hru_wb_aa.txt`
- `channel_yr.txt`

还有一类特殊命名：

- `hydout_aa.txt`
- `hydin_mo.txt`

---

## 2. 三个核心维度

### 2.1 object

表示输出对象是谁。

常见对象包括：

- `basin`
- `hru`
- `hru-lte`
- `lsunit`
- `ru`
- `channel`
- `aquifer`
- `reservoir`
- `hyd`
- `region`

你可以把它理解成：

- 这份文件是在描述哪个层级/哪类实体的结果

---

### 2.2 report

表示输出的内容类型。

常见 report 包括：

- `wb`
  - water balance
- `nb`
  - nutrient balance
- `ls`
  - landscape / sediment related
- `pw`
  - plant water / crop water related
- `crop_yld`
  - crop yield
- `sd`
  - sediment / channel sediment related

你可以把它理解成：

- 这份文件在讲“水量”、“养分”、“泥沙”还是“作物产量”

---

### 2.3 frequency

表示输出频率。

当前已经明确的频率有：

- `da`
  - daily
- `mo`
  - monthly
- `yr`
  - yearly
- `aa`
  - annual average

这里特别注意：

- `aa` 不是“逐年序列”
- `aa` 是 **多年模拟结果的年平均**

所以：

- 如果你要逐日校准，用 `da`
- 如果你要逐月校准，用 `mo`
- 如果你要逐年序列，用 `yr`
- `aa` 更适合做整体统计，不适合时间序列校准

---

## 3. 最常见的几类输出

### 3.1 Basin 级

常见文件：

- `basin_wb_aa.txt`
- `basin_nb_aa.txt`
- `basin_ls_aa.txt`
- `basin_pw_aa.txt`
- `basin_crop_yld_aa.txt`

用途：

- 看整个流域的总量/平均量
- 更偏汇总视角

例如：

- `WYLD`
- `SURQ`
- `PERC`
- `ET`
- `PREC`

---

### 3.2 HRU 级

常见文件：

- `hru_wb_aa.txt`
- `hru_nb_aa.txt`
- `hru_ls_aa.txt`
- `hru_pw_aa.txt`

用途：

- 看每个 HRU 的水文、养分、植被过程
- 更偏空间离散单元视角

---

### 3.3 Channel 级

常见文件：

- `channel_day.txt`
- `channel_mon.txt`
- `channel_yr.txt`
- `channel_aa.txt`

用途：

- 看每条河道 reach 的流量、入流、出流、泥沙等
- 这是目前最接近 `SWAT2012 output.rch` 的一组输出

常见变量：

- `flo_in`
- `flo_out`

注意：

- `channel_*` 是按 **reach**
- 不是按 old-style `subbasin` 直接等价映射

---

### 3.4 Hyd monitoring / recall 级

常见文件：

- `hydout_day.txt`
- `hydout_mon.txt`
- `hydout_yr.txt`
- `hydout_aa.txt`
- `hydin_day.txt`
- `hydin_mon.txt`
- `hydin_yr.txt`
- `hydin_aa.txt`

用途：

- 用于用户定义监测点/控制点
- 更像“我专门布置的观测位置”

常见变量：

- `flo`

注意：

- `hydout_*` 不是 `output.rch` 的直接翻版
- 它更像“用户主动定义的监测点输出”

---

### 3.5 其他对象级

还可能看到：

- `aquifer_*`
- `reservoir_*`
- `lsunit_*`
- `ru_*`
- `region_*`

这些分别对应：

- 地下水对象
- 水库对象
- 景观单元
- 路由单元
- 区域汇总

---

## 4. 如果你习惯了 SWAT2012

### 4.1 SWAT2012 的心智

很多用户最熟悉的是：

- `output.rch`
- `output.sub`
- `output.hru`

例如：

- `output.rch + FLOW_OUT + reach id`

这套心智是：

- 文件少
- 每个文件很大
- 靠列和 id 去找你要的量

---

### 4.2 SWAT+ 的心智

到了 `SWAT+`，同样的问题要先问清楚：

- 你要看哪个对象
- 你要看哪类过程
- 你要什么时间尺度

也就是：

- 先定 `object`
- 再定 `report`
- 再定 `frequency`

---

## 5. `output.rch` 在 SWAT+ 里最接近什么

这是最重要的问题。

### 5.1 最接近的主路线

如果用户在 `SWAT2012` 里最常做的是：

- 从 `output.rch` 抽某个站点/某条 reach 的流量

那么在 `SWAT+` 里最接近的主路线是：

- `channel_*`
- 变量：`flo_out`

也就是：

```text
SWAT2012: output.rch + FLOW_OUT
SWAT+:    channel_*.txt + flo_out
```

这是因为：

- `channel_*` 是 per-reach 输出
- 它最像旧的河道流量输出思路

---

### 5.2 第二条路线

如果用户不是想看“所有 reach 中某一条”，而是：

- 我在模型里定义了一个监测点
- 我就想看这个特定点的流量

那更合适的是：

- `hydout_*`
- 变量：`flo`

也就是：

```text
SWAT+: hydout_*.txt + flo
```

这更像：

- 监测点
- 控制点
- recall 点

---

### 5.3 第三条路线

如果用户其实不是关心某一条河道，而是：

- 整个流域出口总量
- 或整体产流

那更适合：

- `basin_wb_*`
- 常见变量：`WYLD`, `SURQ`

---

## 6. 这不是严格 1:1 映射

`output.rch -> channel_*` 只能说是 **最接近**，不是严格 1:1。

原因有 3 个：

### 6.1 空间层级变了

`SWAT2012` 里：

- subbasin / reach 心智更直接

`SWAT+` 里：

- landscape units
- routing units
- channels

空间离散方式更细，结构更复杂。

---

### 6.2 ID 空间变了

`SWAT2012` 常见心智是：

- subbasin id
- reach id

而 `SWAT+` 里：

- channel id
- gis_id
- hyd object id

这些不一定和旧的 subbasin 编号直接对应。

---

### 6.3 单位可能不同

例如目前调研里已经明确：

- `channel_*` 中的 `flo_out` 是 `ha-m`
- 而用户对 `SWAT2012 FLOW_OUT` 的直觉通常是流量率

所以在迁移用户心智时，必须说明：

- 文件对应关系
- 对象对应关系
- 单位差异

---

## 7. 用户怎么快速判断该看哪个输出

可以按下面这个简单规则判断：

### 7.1 看整个流域

用：

- `basin_*`

例如：

- `basin_wb_yr.txt`

---

### 7.2 看每个 HRU

用：

- `hru_*`

例如：

- `hru_wb_mo.txt`

---

### 7.3 看每条河道的流量

用：

- `channel_*`

例如：

- `channel_yr.txt`
- `channel_mon.txt`

---

### 7.4 看指定监测点

用：

- `hydout_*`
- `hydin_*`

例如：

- `hydout_yr.txt`

---

## 8. 目前 hydroPilot 里的现实情况

当前项目里，`swatplus` output 支持还没补齐。

已经比较明确的是：

- series.py 已经支持：
  - `aa`
  - `yr`
  - `mo`
  - `da`
- 但 series 数据库目前主要还是：
  - `aa`

所以现在的短板不是 SWAT+ 没这些输出，而是：

- 我们自己的 `swatplus` series 库还没把这些系列补全

尤其是：

- `channel_*`
- `hydout_*`
- `hydin_*`
- `basin_wb_*`

这几类流量相关输出，应该优先补齐。

---

## 9. 一句话总结

如果用最短的话总结：

- `SWAT2012` 是“少数几个大文件 + 列/ID 抽取”
- `SWAT+` 是“按对象 + 报告类型 + 时间频率拆成很多文件”

而对于最常见的 `output.rch` 取流量场景：

- **首选**：`channel_* + flo_out`
- **监测点场景**：`hydout_* + flo`
- **全流域汇总场景**：`basin_wb_* + WYLD`

