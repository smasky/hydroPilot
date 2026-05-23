# SWAT+ `calibration.cal` 路线配置草案（贴现有模板风格版）

这份草案专门响应两个约束：

1. `mode` 与 `changeType` 语义重合，不重复造一套字段
2. 模板层尽量贴现有 `swat` / `swatplus` 风格，不额外发明新块

所以目标不是重造 schema，而是：

- 尽量沿用当前 `design / physical / mode / filter`
- 只把 `swatplus` 的落盘目标，从 `fixed_width` 改成 `calibration.cal`

---

## 1. 设计判断

### 1.1 `mode` 直接承接 `CHG_TYPE`

如果走 `calibration.cal`，当前最自然的映射就是：

- `mode: v` -> `absval`
- `mode: a` -> `abschg`
- `mode: r` -> `pctchg`

这样做的好处：

- 用户层不新增 `changeType`
- 保持和当前 `swat` / `general` 的 `mode` 心智一致
- 模板层负责把 `mode` 翻译成 SWAT+ 的 `CHG_TYPE`

---

### 1.2 模板层尽量保留当前结构

用户层最好继续保持：

- `parameters.design`
- `parameters.physical`
- `mode`
- `filter`

不建议新增：

- `apply.route`
- `change`
- `target`
- `objectIds`

也就是说：

- 范围/对象筛选尽量继续统一放在 `filter` 里

---

## 2. 用户层配置草案

```yaml
version: swatplus

basic:
  projectPath: ./Ames_sub1
  workPath: ./workspace
  command: ./swatplus-rel

parameters:
  design:
    - name: esco
      bounds: [0.1, 0.9]

    - name: perco
      bounds: [-15, 15]

    - name: cn2
      bounds: [-8, 8]

  physical:
    - name: esco
      mode: v

    - name: perco
      mode: r

    - name: cn2
      mode: a
      filter:
        cal_group: ["3"]

series:
  - id: flow
    sim:
      file: basin_wb_aa.txt
      variable: WYLD
      id: 1
      period: [1977, 1980]
    obs:
      file: ./obs/flow.csv
      readerType: text
      dateColumn: date
      valueColumn: flow
```

这层的意图是：

- 用户继续按现在熟悉的写法写
- `mode` 不变
- `filter` 也尽量延续
- 只是 `swatplus` 模板内部不再把它展开成 `file.line/start/width`

---

## 3. `filter` 在这条路线里的理解

如果走 `calibration.cal`，`filter` 不应该再理解成：

- fixed-width 写入时的“文件行选择”

而应该理解成：

- calibration 条件翻译输入
- 或模板层对象预筛选输入

也就是说，模板层会把：

```yaml
filter:
  cal_group: ["3"]
```

翻译成接近：

```text
cal_group  null  0  3
```

如果是当前源码未直接支持的筛选条件，例如 `slope range`，模板层则先把它翻译成对象编号列表，再写入 `OBJ_TOT + object ids`。

这里仍然坚持一个原则：

- 用户层继续写 `filter`
- `models/swatplus` 负责把 `filter` 变成：
  - `conditions`
  - 或对象编号列表

这样更贴现有模板风格。

---

## 3.1 `filter` 例子

### 例 1：最简单的单条件

```yaml
physical:
  - name: cn2
    mode: a
    filter:
      cal_group: ["3"]
```

模板层大致翻译成：

```text
cal_group  null  0  3
```

语义：

- 只对 `cal_group = 3` 的对象施加 `cn2` 修改

---

### 例 2：按 `landuse` 过滤

```yaml
physical:
  - name: esco
    mode: v
    filter:
      landuse: ["agrl_lum"]
```

模板层大致翻译成：

```text
landuse  null  0  agrl_lum
```

语义：

- 只对 `landuse = agrl_lum` 的对象施加 `esco` 修改

---

### 例 3：按 `hsg` 过滤

```yaml
physical:
  - name: perco
    mode: r
    filter:
      hsg: ["A"]
```

模板层大致翻译成：

```text
hsg  null  0  A
```

语义：

- 只对 `hsg = A` 的对象施加 `perco` 修改

---

### 例 4：按 `texture` 过滤

```yaml
physical:
  - name: awc
    mode: a
    filter:
      texture: ["SILT_LOAM"]
```

模板层大致翻译成：

```text
texture  null  0  SILT_LOAM
```

语义：

- 只对 `texture = SILT_LOAM` 的对象施加 `awc` 修改

---

### 例 5：多个字段同时过滤

```yaml
physical:
  - name: cn2
    mode: a
    filter:
      cal_group: ["3"]
      landuse: ["agrl_lum"]
```

模板层大致翻译成两条条件记录：

```text
cal_group  null  0  3
landuse    null  0  agrl_lum
```

语义：

- 只对同时满足：
  - `cal_group = 3`
  - `landuse = agrl_lum`
  的对象施加 `cn2` 修改

我当前建议把这个理解成：

- 不同字段之间默认 `AND`

---

### 例 6：同一个字段多个值

```yaml
physical:
  - name: esco
    mode: v
    filter:
      hsg: ["A", "B"]
```

这里有两种可能实现路线：

#### 路线 A：模板层展开成多条条件记录

```text
hsg  null  0  A
hsg  null  0  B
```

#### 路线 B：模板层先转成对象编号列表，再不保留条件

```yaml
filter:
  object_id: [ ... ]
```

我当前更倾向先把这种情况判成：

- 第一版不要急着支持
- 或者只在模板层做“对象列表预展开”

因为需要确认 SWAT+ 多条同字段条件在 calibration 中到底是 OR 还是 AND 语义。

---

### 例 7：范围条件

```yaml
physical:
  - name: res_k
    mode: a
    filter:
      res_pvol:
        range: [10, 50]
```

模板层大致翻译成：

```text
range  res_pvol  10  50
```

语义：

- 只对 `res_pvol` 在 `[10, 50]` 区间内的对象施加参数修改

这类 `range` 我建议单独识别，不要和普通等值条件混着处理。

---

### 例 8：显式对象编号也继续放在 `filter` 里

如果要尽量贴合 `swat2012` 风格，我更建议不要把对象编号单独挂成外层字段。

更贴现有风格的写法应该是：

```yaml
physical:
  - name: cn2
    mode: a
    filter:
      object_id: [1, 3, 5, 8]
```

这里的理解是：

- 用户仍然在写 `filter`
- 只是 `swatplus` 模板内部把 `object_id` 解释成显式对象编号列表

模板层内部大致翻译成：

```text
... OBJ_TOT = 4   1 3 5 8
```

而不是继续生成条件记录。

---

### 例 9：对象编号和其他条件同时存在

```yaml
physical:
  - name: cn2
    mode: a
    filter:
      object_id: [1, 3, 5, 8]
      cal_group: ["3"]
```

推荐语义：

- 先拿 `filter.object_id` 作为候选集合
- 再应用其他 `filter` 条件

即：

```text
候选对象 = [1, 3, 5, 8]
再保留满足 cal_group = 3 的对象
```

这样比“对象列表和条件谁覆盖谁”更稳定。

---

### 例 10：没有 `filter`

```yaml
physical:
  - name: esco
    mode: v
```

模板层：

- `CONDS = 0`
- `OBJ_TOT = 0`
- 不附加条件记录

语义：

- 让该参数直接作用于其对象类型对应的全体对象

---

## 3.2 我当前建议的第一阶段支持范围

### 建议直接支持

- 单字段等值条件
  - `object_id`
  - `cal_group`
  - `landuse`
  - `hsg`
  - `texture`
  - `plant`
  - `pl_class`

### 建议第二阶段再支持

- 多字段组合条件
- 范围条件
- 同字段多值
- `object_id + 其他 filter` 复杂组合

这样做的好处是：

- 第一阶段更容易保证语义不做错
- 不会过早把 `filter` 复杂度拉爆

---

## 3.3 两个关键例子：HRU 指定 ID / HRU 指定 slope 范围

### 例 A：针对 HRU 参数，显式指定 HRU IDs

```yaml
physical:
  - name: cn2
    mode: a
    filter:
      object_id: [12, 18, 21]
```

直觉语义：

- 只对 HRU `12, 18, 21` 施加 `cn2` 修改

模板层翻译后的 calibration 记录心智：

```text
cn2  abschg  -5.000...  0  0  0  0  0  0  0  3  12 18 21
```

这里：

- `CONDS = 0`
- `OBJ_TOT = 3`
- 行尾对象编号：
  - `12 18 21`

这件事的性质：

- 这是 **SWAT+ calibration 原生能力**
- hydroPilot 不需要发明条件语法
- 只需要把 `filter.object_id` 正确放到记录行尾

---

### 例 B：针对 HRU 参数，按 slope 范围筛选

```yaml
physical:
  - name: cn2
    mode: a
    filter:
      slope:
        range: [10, 20]
```

直觉语义：

- 只对 slope 在 `10 ~ 20` 之间的 HRU 施加 `cn2` 修改

但当前源码的现实情况是：

- 我没有看到一个已经确认的 SWAT+ calibration 原生条件：
  - `range slope ...`

所以更稳的路线不是直接写：

```text
range slope 10 20
```

而是：

- 在模板层先读 SWAT+ 项目里的 HRU 元数据
- 把 slope 在 `[10, 20]` 范围内的 HRU 找出来
- 再把这批 HRU 编号展开成：

```yaml
filter:
  object_id: [12, 18, 21, 34]
```

最后真正写进 `calibration.cal` 的不是 `range slope ...`，而是：

```text
cn2  abschg  -5.000...  0  0  0  0  0  0  0  4  12 18 21 34
```

也就是：

- `CONDS = 0`
- `OBJ_TOT = 4`
- 对象列表写成行尾编号

这件事的性质：

- 这是 **hydroPilot 模板层增强能力**
- 不是我现在已经确认的 SWAT+ calibration 原生 `CONDS` 语法能力

所以这类支持如果要做，文档必须写清：

- 用户写的是 `filter.slope.range`
- 但模板层会把它**前置翻译成 `filter.object_id`**
- 不承诺直接落成 SWAT+ 原生 `range slope` 条件

---

### 例 C：HRU + 显式 IDs + slope 范围同时使用

```yaml
physical:
  - name: cn2
    mode: a
    filter:
      object_id: [10, 12, 18, 21, 40]
      slope:
        range: [10, 20]
```

推荐语义：

- 先取候选对象 `[10, 12, 18, 21, 40]`
- 再按 slope 范围过滤
- 最后写入：

```text
... OBJ_TOT = 3   12 18 21
```

这条规则的优点：

- 很符合直觉
- 不需要把 writer 变复杂
- 条件语义都在模板层完成

---

## 3.4 这几个例子带来的重要判断

如果按你关心的真实使用场景看，`swatplus calibration` 路线最自然会形成两类选择能力：

### A. 原生 calibration 选择

- `filter.object_id`
- 已确认存在的 `CONDS` 条件字段

### B. 模板层预处理选择

- `slope` 范围
- 更复杂的 HRU 属性组合
- 任何当前 calibration 源码未明确支持、但项目文件中可推导的对象属性

也就是说，很多“常用筛选能力”不一定要强行映射成 `CONDS` 原生语法。

更稳妥的是：

- **在模板层先把它翻译成对象列表**
- 然后 calibration 文件里只写对象编号

这个判断我建议后面重点保留。

---

## 4. 内部展开后的 general 风格草案

这一层不是给用户看的，而是说明：

- 模板层如何把现有 `physical` 风格转换成 writer 可消费的数据

```yaml
version: general

parameters:
  design:
    - name: esco
      type: float
      bounds: [0.1, 0.9]

    - name: perco
      type: float
      bounds: [-15, 15]

    - name: cn2
      type: float
      bounds: [-8, 8]

  physical:
    - writerType: record_text
      file:
        name: calibration.cal
      payload:
        header:
          - "Number of parameters:"
        records:
          - paramRef: esco
            fields:
              NAME: esco
              CHG_TYPE: absval
              CONDS: 0
              LYR1: 0
              LYR2: 0
              YEAR1: 0
              YEAR2: 0
              DAY1: 0
              DAY2: 0
              OBJ_TOT: 0
            tail: []
            attachments: []

          - paramRef: perco
            fields:
              NAME: perco
              CHG_TYPE: pctchg
              CONDS: 0
              LYR1: 0
              LYR2: 0
              YEAR1: 0
              YEAR2: 0
              DAY1: 0
              DAY2: 0
              OBJ_TOT: 0
            tail: []
            attachments: []

          - paramRef: cn2
            fields:
              NAME: cn2
              CHG_TYPE: abschg
              CONDS: 1
              LYR1: 0
              LYR2: 0
              YEAR1: 0
              YEAR2: 0
              DAY1: 0
              DAY2: 0
              OBJ_TOT: 0
            tail: []
            attachments:
              - [cal_group, null, 0, "3"]
```

这里需要注意的点：

- `paramRef`
  - 只是内部引用 design 变量值
- `CHG_TYPE`
  - 来自 `mode` 映射
- `attachments`
  - 来自 `filter -> calibration conditions`
- `tail`
  - 来自 `filter.object_id`

---

## 5. 为什么这一版更贴现有风格

### 5.1 用户层不新增 route / apply / change 三件套

这一版改成：

- 用户继续写 `mode`
- 用户继续写 `filter`
- 模板内部自己翻译

这明显更贴当前仓库的习惯。

---

### 5.2 `physical` 继续承担“参数怎么作用”的角色

当前项目里，`physical` 本来就是：

- 参数如何落到模型输入的桥接层

所以现在改成 calibration 路线后，也不需要把这层职责打碎。

只是从：

- 文件坐标写入

变成：

- calibration 记录生成

---

### 5.2.1 显式对象编号也继续留在 `filter`

如果要尽量贴 `swat2012` 风格，我建议：

- 不额外发明平级字段 `objectIds`
- 而是继续统一收在 `filter`

例如：

```yaml
filter:
  object_id: [12, 18, 21]
```

这样用户层更统一：

- `subbasin`
- `land_use`
- `soil`
- `slope`
- `object_id`

都还是“筛选范围”的一部分。

---

### 5.3 外层 writer 仍然不带 SWAT+ 语义

这一版里：

- `record_text` 只负责写：
  - header
  - records
  - tail
  - attachments

它不需要知道：

- `cal_group` 是什么
- `cn2` 是什么
- `mode: a` 在 SWAT+ 里意味着什么

这些都继续留在 `models/swatplus`

---

## 6. 我当前建议的最小映射规则

### 6.1 `mode -> CHG_TYPE`

建议先定成：

- `v -> absval`
- `a -> abschg`
- `r -> pctchg`

### 6.2 `filter -> conditions / object list`

建议第一阶段只支持最少一组已确认字段：

- `object_id`
- `cal_group`
- `hsg`
- `texture`
- `plant`
- `pl_class`
- `landuse`

并由模板统一翻译成：

- 对象列表
- 普通条件记录 `var alt targ targc`
- 或少量范围条件

### 6.3 多参数聚合成一个 `calibration.cal`

建议不要再沿用 fixed-width 那种“一参数一个物理写入项”的心智。

更自然的是：

- 模板层先把所有 calibration 参数聚合
- 最终只生成一个 `calibration.cal` 文件任务

---

## 7. 这一版仍然留待你拍板的点

### 7.1 `filter` 字段名是否继续叫 `filter`

我当前倾向：

- 继续叫 `filter`

因为这最贴现有风格。

但含义要在 `swatplus` 文档里改清楚：

- 在 calibration 路线下，它不再是“行选择”
- 而是“条件翻译输入 / 对象预筛选输入”

### 7.2 `cal_group` 是否作为第一优先支持条件

我当前倾向：

- 是

因为它最贴 SWAT+ 官方 calibration 语义，也最容易解释。

### 7.3 `record_text` 是否是合适的通用 writer 名

这只是占位名，不是结论。

你后面如果觉得：

- `record_text`
- `block_text`
- `table_text`

哪一个更贴设计原则，可以再收敛。

### 7.4 `object_id` 这个 key 是否合适

如果显式对象编号也收进 `filter`，还需要拍板：

- `object_id`
- `id`
- `unit_id`

哪个名字更顺手。

我当前偏向：

- `object_id`

原因：

- 不会和 `series.sim.id` 混
- 也不预设它一定是 HRU / subbasin / channel 的哪一种

---

## 8. 当前最核心的一句话

如果按你这次的约束继续收敛，最合理的方向不是：

- 重新发明一套 SWAT+ 用户 DSL

而是：

- 用户层继续沿用 `mode + filter + physical`
- `models/swatplus` 内部把它翻译成 `calibration.cal` 记录
- 通用 writer 只负责写结构化记录文本
