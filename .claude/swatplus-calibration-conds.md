# SWAT+ `calibration.cal` 中 `CONDS` 语法清单

这份文档只回答一个问题：

- `CONDS` 后面到底能跟哪些语法
- 这些条件语法在 SWAT+ 源码里当前支持到什么程度

---

## 1. 先说结论

按当前 SWAT+ 源码，`CONDS` 后面的条件语法核心分成两类：

1. 普通条件行
2. `range` 条件行

`CONDS` 本身只是：

- 后续条件记录条数

真正的条件内容写在后面的条件行里。

---

## 2. 条件记录的两类基础语法

### 2.1 普通条件行

基础结构：

```text
<var> <alt> <targ> <targc>
```

这个结构来自 SWAT+ 源码里的 `calibration_conditions` 定义。

字段槽位：

- `var`
  - 条件字段名
- `alt`
  - 辅助字段 / 比较辅助槽位
- `targ`
  - 数值目标
- `targc`
  - 字符目标

注意：

- 这只是结构形态
- 并不是所有字段在所有条件下都同样重要
- 从当前源码实现看，很多字符串类条件真正主要使用的是 `targc`

---

### 2.2 `range` 条件行

基础结构：

```text
range <var> <val1> <val2>
```

它表示：

- 对某个变量按数值区间筛选

也就是说：

- 只对某个属性值位于 `[val1, val2]` 范围内的对象生效

---

## 3. 当前源码确认支持的普通条件字段

按 `cal_conditions.f90` 当前实现，普通条件里已明确识别的 `var` 包括：

- `hsg`
- `res_typ`
- `texture`
- `plant`
- `pl_class`
- `landuse`
- `cal_group`

这些是当前最重要的条件字段集合。

---

## 4. 每种普通条件的大致语义

下面这些解释，基于当前 `cal_conditions.f90` 的判断逻辑。

### 4.1 `hsg`

表示按水文土壤组筛选：

```text
hsg <alt> <targ> <targc>
```

可理解为：

- 只对 `hydgrp` 匹配的对象生效

---

### 4.2 `texture`

表示按土壤质地筛选：

```text
texture <alt> <targ> <targc>
```

可理解为：

- 只对 `soil texture` 匹配的对象生效

---

### 4.3 `plant`

表示按植物类型筛选：

```text
plant <alt> <targ> <targc>
```

可理解为：

- 只对 plant 匹配的对象生效

---

### 4.4 `pl_class`

表示按 plant class 筛选：

```text
pl_class <alt> <targ> <targc>
```

可理解为：

- 只对某类 plant class 生效

---

### 4.5 `landuse`

表示按土地利用管理类型筛选：

```text
landuse <alt> <targ> <targc>
```

可理解为：

- 只对某类 `land_use_mgt` 对象生效

---

### 4.6 `cal_group`

表示按 calibration group 筛选：

```text
cal_group <alt> <targ> <targc>
```

可理解为：

- 只对 calibration group 匹配的对象生效

注意：

- SWAT+ 文档字段常写作 `cal_grp`
- 但当前 calibration 源码判断里识别的是 `cal_group`
- 这两个名字不能直接混用，需要后续映射时特别小心

---

### 4.7 `res_typ`

表示按 reservoir type / reservoir 相关类别筛选：

```text
res_typ <alt> <targ> <targc>
```

可理解为：

- 只对 reservoir type 匹配的对象生效

---

## 5. 当前源码确认支持的 `range` 条件

当前直接在 `cal_conditions.f90` 里明确看到的 `range` 变量是：

- `res_pvol`

所以一个已经比较明确成立的 `range` 写法是：

```text
range res_pvol 10 50
```

可理解为：

- 只对 `res_pvol` 落在 `[10, 50]` 区间内的 reservoir 对象生效

---

## 6. 示例

### 6.1 按 `hsg` 筛选

```text
hsg null 0 A
```

直觉化理解：

- 只对 `hsg = A` 的对象生效

---

### 6.2 按 `texture` 筛选

```text
texture null 0 SILT_LOAM
```

直觉化理解：

- 只对 `texture = SILT_LOAM` 的对象生效

---

### 6.3 按 `landuse` 筛选

```text
landuse null 0 agrl_lum
```

直觉化理解：

- 只对 `landuse = agrl_lum` 的对象生效

---

### 6.4 按 `cal_group` 筛选

```text
cal_group null 0 3
```

直觉化理解：

- 只对 `calibration group = 3` 的对象生效

---

### 6.5 按区间筛选

```text
range res_pvol 10 50
```

直觉化理解：

- 只对 `res_pvol` 在 10 到 50 范围内的对象生效

---

## 7. 当前最稳的认知边界

可以比较稳地说：

- `CONDS` 后面不是自由表达式语言
- 它是 SWAT+ 源码里写死支持的一小组条件语法
- 目前最明确的是：
  - 一组普通条件字段
  - 一种 `range` 语法

不应该先假设：

- 任意项目字段都能直接拿来写条件
- `calibration.cal` 条件支持一套开放 DSL

---

## 8. 对 hydroPilot 的直接启发

如果以后 hydroPilot 走 `calibration.cal` 路线，条件层不应该先设计成开放自由文本。

更稳妥的思路是：

- 先把当前源码支持的条件字段收成有限枚举
- builder 负责把用户条件翻译成：
  - 普通条件记录
  - 或 `range` 条件记录

也就是说，内部表达更应该像：

```yaml
conditions:
  - kind: field_match
    field: landuse
    value: agrl_lum
```

或者：

```yaml
conditions:
  - kind: range
    field: res_pvol
    min: 10
    max: 50
```

而不是直接把一整段 SWAT+ 原始条件文本裸露给用户。

---

## 9. 当前仍需继续核实的点

虽然这份清单已经比之前更稳，但仍有一些点值得后续继续核实：

- `alt` 字段在不同条件类型下的真实作用
- `targ` 与 `targc` 的使用边界
- 是否还有未在当前入口处显式列出、但在别处间接支持的条件字段
- 不同 `ob_typ` 下条件字段是否存在适用范围差异

所以这份文档目前适合作为：

- 条件语法范围判断依据
- schema / builder 设计输入
- 避免过度抽象或过度开放的依据

---

## 10. 参考源码

- `calibration_data_module.f90`
- `cal_parmchg_read.f90`
- `cal_conditions.f90`
