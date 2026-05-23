# SWAT+ `filter` 到 `calibration.cal` general 层的映射草案

这份文档只回答一个问题：

- 用户层继续写 `filter`
- 那么 `models/swatplus` 应该怎样把它翻译到 general 层

这里的目标是两件事同时成立：

1. 用户写法尽量贴近现在 `swat2012`
2. general / writer 层不要带太多 SWAT+ 业务判断

---

## 1. 先说结论

如果 `swatplus` 走 `calibration.cal`，那用户层 `filter` 建议分成两类理解：

1. **可直接翻译成 calibration 条件行**
2. **不能稳定直译，需要模板层先做对象预筛选**

对应到 general 层：

- 第一类落到 `file.attachments`
- 第二类落到 `file.tail`

也就是说：

- `attachments` 表示 SWAT+ 原生 condition lines
- `tail` 表示模板层已经算好的 object ids

---

## 2. 用户层仍然保留 `filter`

这一点我建议不要改。

也就是用户仍然写：

```yaml
physical:
  - name: cn2
    mode: a
    filter:
      cal_group: [3]
```

而不是引入新的：

- `conditions`
- `objectIds`
- `scope`
- `targetObjects`

原因很简单：

- 这和当前 `swat2012` 的习惯最接近
- 用户只关心“筛谁”
- 不需要关心最后是翻成 condition line，还是翻成 object ids

这件事应该由 `models/swatplus` 负责。

---

## 3. 第一类：可直接翻译成 `attachments`

这类字段的特点是：

- SWAT+ calibration 源码本身有对应 condition 语法
- 模板层不需要先扫描项目对象再折成 id 列表

当前基于源码/pySWATPlus，比较稳的候选包括：

- `cal_group`
- `landuse`
- `hsg`
- `texture`
- `plant`
- `pl_class`
- `res_typ`

这类映射规则可以统一理解成：

```text
filter.<key> -> 1 条或多条 attachment
```

---

## 4. 第二类：先做对象预筛选，再落到 `tail`

这类字段的特点是：

- 用户想按某种对象属性筛选
- 但 SWAT+ calibration 不一定有稳定、通用的原生条件表达

这时模板层就不应该硬造 condition line，而应该：

1. 读取项目元数据
2. 找出匹配对象
3. 生成对象 id 列表
4. 写入 `OBJ_TOT + tail`

这类典型例子包括：

- `object_id`
- `hru`
- `subbasin` 或类似上游友好别名
- `slope`
- 未来其他需要靠项目扫描才能确定作用对象的条件

注意：

- 这些字段是“用户筛选语义”
- 不代表它们会原样出现在 `calibration.cal`

---

## 5. 映射总表

### 5.1 直接进 `attachments` 的字段

| 用户层 `filter` 字段 | 模板层动作 | general 层落点 |
| --- | --- | --- |
| `cal_group` | 生成 `cal_group null 0 <value>` 条件行 | `file.attachments` |
| `landuse` | 生成 `landuse null 0 <value>` 条件行 | `file.attachments` |
| `hsg` | 生成 `hsg null 0 <value>` 条件行 | `file.attachments` |
| `texture` | 生成 `texture null 0 <value>` 条件行 | `file.attachments` |
| `plant` | 生成 `plant null 0 <value>` 条件行 | `file.attachments` |
| `pl_class` | 生成 `pl_class null 0 <value>` 条件行 | `file.attachments` |
| `res_typ` | 生成 `res_typ null 0 <value>` 条件行 | `file.attachments` |

### 5.2 先变对象列表，再进 `tail` 的字段

| 用户层 `filter` 字段 | 模板层动作 | general 层落点 |
| --- | --- | --- |
| `object_id` | 直接作为对象 id 列表 | `file.tail` |
| `hru` | 解析为 HRU 对象 id 列表 | `file.tail` |
| `subbasin` | 先找该子流域相关对象，再转对象 id 列表 | `file.tail` |
| `slope` | 先扫描项目对象，筛出满足条件的对象 id | `file.tail` |
| 其他项目属性筛选 | 先查元数据，再转对象 id 列表 | `file.tail` |

---

## 6. 最重要的设计边界

### 6.1 用户层不区分 `attachments` / `tail`

用户只写：

```yaml
filter:
  ...
```

不要要求用户自己决定：

- 这是 condition line
- 还是 object tail

这会把 SWAT+ 内部实现细节暴露出去。

---

### 6.2 template 层负责决定翻译路线

`models/swatplus` 需要做的其实是：

```text
filter
  -> classify
  -> attachment conditions
  -> object ids
  -> general file.*
```

这也是为什么这部分逻辑必须留在模板层，而不是塞进通用 writer。

---

### 6.3 writer 只认格式化结果

writer 不应该知道：

- 什么是 `landuse`
- 什么是 `cal_group`
- 什么是 `hru`
- 什么是 `subbasin`

writer 只看到：

- `content`
- `tail`
- `attachments`

然后把它们按格式写出去。

---

## 7. 单字段示例

### 7.1 `cal_group`

用户层：

```yaml
physical:
  - name: cn2
    mode: a
    filter:
      cal_group: [3]
```

模板层判断：

- `cal_group` 是 SWAT+ 原生条件
- 直接翻成 attachment

general 层：

```yaml
file:
  name: calibration.cal
  line: 6
  content:
    format: "{0:<12s}{1:<21s}{2:>14.6f}{3:>9d}{4:>8d}{5:>7d}{6:>8d}{7:>9d}{8:>8d}{9:>5d}{10:>7d}"
    values: [cn2, abschg, "@value", 1, 0, 0, 0, 0, 0, 0, 0]
  attachments:
    - format: "{0:<12s}{1:<10s}{2:>8d}{3:>8d}"
      values: [cal_group, null, 0, 3]
```

---

### 7.2 `landuse`

用户层：

```yaml
physical:
  - name: esco
    mode: v
    filter:
      landuse: [agrl_lum]
```

general 层：

```yaml
file:
  name: calibration.cal
  line: 5
  content:
    format: "{0:<12s}{1:<21s}{2:>14.6f}{3:>9d}{4:>8d}{5:>7d}{6:>8d}{7:>9d}{8:>8d}{9:>5d}{10:>7d}"
    values: [esco, absval, "@value", 1, 0, 0, 0, 0, 0, 0, 0]
  attachments:
    - format: "{0:<12s}{1:<10s}{2:>8d}{3:<12s}"
      values: [landuse, null, 0, agrl_lum]
```

---

### 7.3 `hsg`

用户层：

```yaml
physical:
  - name: perco
    mode: r
    filter:
      hsg: [A]
```

general 层：

```yaml
file:
  name: calibration.cal
  line: 5
  content:
    format: "{0:<12s}{1:<21s}{2:>14.6f}{3:>9d}{4:>8d}{5:>7d}{6:>8d}{7:>9d}{8:>8d}{9:>5d}{10:>7d}"
    values: [perco, pctchg, "@value", 1, 0, 0, 0, 0, 0, 0, 0]
  attachments:
    - format: "{0:<12s}{1:<10s}{2:>8d}{3:<8s}"
      values: [hsg, null, 0, A]
```

---

## 8. 对象预筛选示例

### 8.1 指定对象 id

用户层：

```yaml
physical:
  - name: cn2
    mode: a
    filter:
      object_id: [12, 18, 21]
```

模板层判断：

- 这是显式对象选择
- 不生成 attachment
- 直接写对象尾部

general 层：

```yaml
file:
  name: calibration.cal
  line: 6
  content:
    format: "{0:<12s}{1:<21s}{2:>14.6f}{3:>9d}{4:>8d}{5:>7d}{6:>8d}{7:>9d}{8:>8d}{9:>5d}{10:>7d}"
    values: [cn2, abschg, "@value", 0, 0, 0, 0, 0, 0, 0, 3]
  tail:
    format: "{0:>5d}{1:>5d}{2:>5d}"
    values: [12, 18, 21]
```

---

### 8.2 指定子流域

用户层：

```yaml
physical:
  - name: cn2
    mode: a
    filter:
      subbasin: [3]
```

模板层判断：

- `subbasin` 不是直接写进 calibration 条件行
- 需要先用项目元数据找到该子流域相关对象
- 再折成对象 id 列表

general 层示意：

```yaml
file:
  name: calibration.cal
  line: 6
  content:
    format: "{0:<12s}{1:<21s}{2:>14.6f}{3:>9d}{4:>8d}{5:>7d}{6:>8d}{7:>9d}{8:>8d}{9:>5d}{10:>7d}"
    values: [cn2, abschg, "@value", 0, 0, 0, 0, 0, 0, 0, 4]
  tail:
    format: "{0:>5d}{1:>5d}{2:>5d}{3:>5d}"
    values: [12, 18, 21, 34]
```

这里的 `12, 18, 21, 34` 只是示意。

---

### 8.3 指定 slope 范围

用户层：

```yaml
physical:
  - name: cn2
    mode: a
    filter:
      slope:
        min: 10
        max: 20
```

模板层判断：

- 不假定 SWAT+ 原生支持 `slope` 条件行
- 先扫描项目对象
- 找出 `slope in [10, 20]` 的对象
- 再写入 `tail`

general 层示意：

```yaml
file:
  name: calibration.cal
  line: 6
  content:
    format: "{0:<12s}{1:<21s}{2:>14.6f}{3:>9d}{4:>8d}{5:>7d}{6:>8d}{7:>9d}{8:>8d}{9:>5d}{10:>7d}"
    values: [cn2, abschg, "@value", 0, 0, 0, 0, 0, 0, 0, 4]
  tail:
    format: "{0:>5d}{1:>5d}{2:>5d}{3:>5d}"
    values: [12, 18, 21, 34]
```

---

## 9. 混合示例

这类情况最接近真实使用：

- 一部分条件可以直译成 attachment
- 另一部分需要先转成对象 ids

例如：

```yaml
physical:
  - name: cn2
    mode: a
    filter:
      cal_group: [3]
      slope:
        min: 10
        max: 20
```

模板层处理：

1. `cal_group` -> attachment
2. `slope` -> 先筛对象 ids -> tail

general 层：

```yaml
file:
  name: calibration.cal
  line: 6
  content:
    format: "{0:<12s}{1:<21s}{2:>14.6f}{3:>9d}{4:>8d}{5:>7d}{6:>8d}{7:>9d}{8:>8d}{9:>5d}{10:>7d}"
    values: [cn2, abschg, "@value", 1, 0, 0, 0, 0, 0, 0, 4]
  tail:
    format: "{0:>5d}{1:>5d}{2:>5d}{3:>5d}"
    values: [12, 18, 21, 34]
  attachments:
    - format: "{0:<12s}{1:<10s}{2:>8d}{3:>8d}"
      values: [cal_group, null, 0, 3]
```

也就是说：

- `CONDS = 1`
- `OBJ_TOT = 4`

这两部分可以同时存在。

---

## 10. 对 user 层的建议

如果目标是“尽量像 SWAT2012”，我建议用户层先只暴露下面这些风格：

### 10.1 直接条件类

```yaml
filter:
  cal_group: [3]
  landuse: [agrl_lum]
  hsg: [A]
```

### 10.2 对象筛选类

```yaml
filter:
  object_id: [12, 18, 21]
```

```yaml
filter:
  subbasin: [3]
```

```yaml
filter:
  slope:
    min: 10
    max: 20
```

---

## 11. 我现在的判断

这一版最稳的地方在于：

- 用户层没有长出新概念
- template 层承担模型知识翻译
- writer 保持通用

如果后面继续往实现走，我建议模板层内部至少拆成两步：

1. `filter -> condition specs + object selection specs`
2. `condition specs/object ids -> general file.content/tail/attachments`

这样结构最清楚，也不会把 SWAT+ 语义灌进 writer。

