# SWAT+ `calibration.cal` 模版草案

这份文档的目的不是定义 hydroPilot 最终实现，而是把当前已经确认的 `calibration.cal` 结构整理成一个可阅读、可讨论的参考稿，便于后续决定 writer 抽象。

---

## 1. 当前已确认的事实

- `calibration.cal` 是 SWAT+ `Change` 类输入文件之一。
- `cal_parms.cal` 是参数定义/支持表。
- `calibration.cal` 是一次仿真中实际施加参数修改的记录文件。
- `pySWATPlus` 真实生成 `calibration.cal` 的方式已经可以作为一个重要参考：
  - 一行 `Number of parameters:`
  - 一行参数个数
  - 一行表头
  - 后续每个参数一条主记录
  - 如果该参数有对象列表，则对象编号追加在主记录行尾
  - 如果该参数有条件，则条件记录写在该参数主记录之后的新行
- `pySWATPlus` 主记录表头明确包含：
  - `NAME`
  - `CHG_TYPE`
  - `VAL`
  - `CONDS`
  - `LYR1`
  - `LYR2`
  - `YEAR1`
  - `YEAR2`
  - `DAY1`
  - `DAY2`
  - `OBJ_TOT`

参考来源：

- SWAT+ `file.cio`
- SWAT+ 源码 `cal_parm_select.f90`
- SWAT+ 源码 `calibration_data_module.f90`
- `pySWATPlus/txtinout_reader.py`

---

## 2. 基于 `pySWATPlus` 真实生成逻辑的 `calibration.cal` 模版

下面这个示例尽量贴近 `pySWATPlus` 的真实生成方式。

关键点：

- 一个参数先有一条**主记录**
- 如果有对象列表，编号会直接追加在主记录行尾
- 如果 `conds > 0`，后面继续跟**条件记录**

下面的表头和主记录风格，按 `pySWATPlus` 当前代码中的字段顺序与列宽语义来展示：

- `NAME`: 12
- `CHG_TYPE`: 8
- `VAL`: 16（并有专门格式化）
- `CONDS`: 16
- `LYR1`: 8
- `LYR2`: 8
- `YEAR1`: 8
- `YEAR2`: 8
- `DAY1`: 8
- `DAY2`: 8
- `OBJ_TOT`: 8

```text
Number of parameters:
3

NAME        CHG_TYPE             VAL    CONDS    LYR1    LYR2   YEAR1   YEAR2    DAY1    DAY2OBJ_TOT
esco          absval    0.500000000000        0       0       0       0       0       0    0      0

perco         pctchg  -15.000000000000        0       0       0       0       0       0    0      0

cn2          abschg   -5.000000000000        1       0       0       0       0       0    0      2       1    3
cal_grp      null                  3    null
```

这个示例表达的意思：

- 第 1 条参数 `esco`
  - 主记录中 `conds = 0`
  - `OBJ_TOT = 0`
  - 所以后面没有附加行
- 第 2 条参数 `perco`
  - 主记录中 `conds = 0`
  - `OBJ_TOT = 0`
  - 所以后面没有附加行
- 第 3 条参数 `cn2`
  - 主记录中 `conds = 1`
  - `OBJ_TOT = 2`
  - 对象编号 `1 3` 直接追加在主记录同一行尾
  - 所以后面多跟 1 行条件记录

这比之前那种把 `OBJ_1 / OBJ_2` 单独画成固定表头列的写法更接近真实生成逻辑。

---

## 3. 主记录字段

根据 `pySWATPlus` 当前真实写法，主记录表头是：

```text
NAME  CHG_TYPE  VAL  CONDS  LYR1  LYR2  YEAR1  YEAR2  DAY1  DAY2  OBJ_TOT
```

字段语义：

- `name`
  - 参数名
- `chg_typ`
  - 修改类型
- `val`
  - 修改值
- `conds`
  - 条件记录条数
- `lyr1`, `lyr2`
  - 分层范围
- `year1`, `year2`
  - 年范围
- `day1`, `day2`
  - 日范围
- `OBJ_TOT`
  - 对象编号数量

注意：

- `CONDS` 不是条件字符串，而是条件记录条数
- `OBJ_TOT` 不是对象列表本身，而是对象编号数量
- 对象编号本身在 `pySWATPlus` 里会直接追加在主记录末尾
- `pySWATPlus` 的输出更像“定宽主记录 + 变长对象尾部 + 附加条件行”

---

## 4. 条件记录

如果主记录里的 `CONDS > 0`，后面继续写条件记录。

当前从源码能确认，条件结构至少涉及这些槽位：

```text
var  alt  targ  targc
```

它们表示一条条件，而不是塞回主记录的一列文本。

示意：

```text
cal_grp null 3 null
```

这里更接近“一个条件对象”，而不是一个 `CONDS` 文本单元格。

---

## 5. 对象编号列表

`pySWATPlus` 当前的真实生成方式不是把对象编号另起一行，而是：

- 先在主记录里写 `OBJ_TOT`
- 如果 `OBJ_TOT > 0`
- 再把对象编号直接追加到主记录行尾

示意：

```text
cn2   abschg  ...  OBJ_TOT=2       1    3
```

表示这条参数修改规则只作用于对象 `1` 和 `3`。

---

## 6. 可从这个文件抽象出的核心元素

从 hydroPilot 的视角看，`calibration.cal` 的一条记录更像是一个“参数变更规则”，而不是“文件坐标写入指令”。

建议先把它理解成以下字段集合：

- `parameter`
  - 官方 calibration 参数名
  - 例如 `esco`、`cn2`、`alpha`
- `changeType`
  - 参数修改方式
  - 当前已明确见到的常见值：
    - `absval`
    - `abschg`
    - `pctchg`
- `value`
  - 修改值
- `conditions`
  - 0 到多条条件记录
  - 例如 `cal_grp`
- `layer range`
  - `lyr1`, `lyr2`
  - 适合土壤分层参数
- `time range`
  - `year1`, `year2`, `day1`, `day2`
- `objects`
  - 0 到多条对象编号
  - 在 `pySWATPlus` 的实际文件里，这些编号直接追加在主记录行尾

---

## 7. 用结构化数据表示时，大概会长什么样

### 4.1 无条件、全局生效

```yaml
- parameter: esco
  changeType: absval
  value: 0.5
  layerStart: 0
  layerEnd: 0
  yearStart: 0
  yearEnd: 0
  dayStart: 0
  dayEnd: 0
  conditions: []
  objects: []
```

### 4.2 带条件和对象选择

```yaml
- parameter: cn2
  changeType: abschg
  value: -5
  layerStart: 0
  layerEnd: 0
  yearStart: 0
  yearEnd: 0
  dayStart: 0
  dayEnd: 0
  conditions:
    - var: cal_grp
      alt: null
      target: 3
      targetCompare: null
  objects: [1, 3]
```

---

## 8. 和当前 `fixed_width` 心智的根本区别

当前 `fixed_width` 的核心输入单位是：

- 文件名
- 行号
- 起始列
- 宽度
- 精度

也就是：

```text
parameter -> file position -> writer
```

而 `calibration.cal` 更像是：

```text
parameter -> change record -> writer
```

差异不在于“是不是文本文件”，而在于：

- `fixed_width` 写的是坐标
- `calibration.cal` 写的是规则记录

---

## 9. 如果后续要抽象 writer，最值得观察的点

先不下最终结论，但可以先用这个模版去判断下面 3 个问题：

### 6.1 writer 的输入单位应该是什么

候选思路：

- 一条 change record
- 一组 change records

而不是单纯的 `file.line.start.width`

### 6.2 `conditions` 是否需要保持弱语义

建议暂时只把它看作：

- 条件记录数组
- 每条记录是一个简单结构体

避免在通用层硬编码 SWAT+ 业务语义。

### 6.3 `objects` 是否可以统一抽成 ID 列表

例如：

- 不在 writer 层区分 HRU / aquifer / channel
- 只让模型模板负责决定“这些 ID 是什么对象”

---

## 10. 当前更稳妥的工程判断

如果以后要让 hydroPilot 支持 `swatplus -> calibration.cal`，更自然的内部产物应该不是：

```yaml
file:
  name:
  line:
  start:
  width:
```

而更像：

```yaml
change:
  parameter: esco
  changeType: absval
  value: 0.5
  layerStart: 0
  layerEnd: 0
  yearStart: 0
  yearEnd: 0
  dayStart: 0
  dayEnd: 0
  conditions: []
  objects: []
```

至于最终 writer 要不要直接围绕这个结构命名，还需要结合现有设计原则继续收敛。

---

## 11. 当前仍未完全钉死的点

这些点还需要继续核实源码或真实样例：

- `changeType` 的完整枚举集合
- `conditions` 的完整表达范围
- `pySWATPlus` 当前写法和 SWAT+ 原生手写样例是否完全一致
- 条件记录的完整语义边界
- `YEAR1/YEAR2/DAY1/DAY2` 在哪些参数类别上真正生效
- 官方原生 `calibration.cal` 示例是否还有额外版式要求

所以这份文档目前适合作为：

- 架构讨论材料
- schema 草案参考
- writer 抽象讨论输入

而不适合作为最终实现规范。
