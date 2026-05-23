# SWAT+ `calibration.cal` General 层格式草案

这份文档只回答一个问题：

- 如果 `swatplus` 改走 `calibration.cal`
- 同时仍然保持 `swat2012 -> template -> general` 这一套风格
- 那么展开后的 general 层 `physical.file` 应该长什么样

这里不讨论用户层最终长什么样，只讨论 **template 展开之后** 的 general 结果。

---

## 1. 先说结论

当前这条路线下，我建议 general 层保持下面这个方向：

```yaml
physical:
  - name:
    type:
    bounds:
    mode:
    writerType:
    file:
      name:
      line:
      content:
        format:
        values:
      tail:
        format:
        values:
      attachments:
        - format:
          values:
```

这版的核心点有 4 个：

1. 继续保留 `file`
2. `content / tail / attachments` 都是“按行渲染”
3. 每一个位置都显式带格式
4. writer 只负责格式化写出，不承担 SWAT+ 业务判断

---

## 2. 为什么这样更合适

### 2.1 跟现有 general 层更接近

现在仓库里，SWAT2012 展开后的 general 层本来就是：

```yaml
physical:
  - name: CN2
    type: float
    mode: r
    writerType: fixed_width
    file:
      name: 000010001.mgt
      line: 11
      start: 1
      width: 16
      precision: 4
```

所以 SWAT+ 这边如果也把最终目标放在 `file.*` 下，整体感觉是统一的。

差别只在于：

- SWAT2012 是“单点替换”
- SWAT+ `calibration.cal` 是“整行组织”

但二者都还是 `physical -> file` 这一层。

---

### 2.2 general 层允许保留明确字段语义

到 general 层时，模板已经展开完了，所以这里不需要再刻意追求“完全无语义”。

保留这些字段是合理的：

- `name`
- `type`
- `bounds`
- `mode`
- `writerType`
- `file`

这里的语义边界应该是：

- **template** 负责把模型知识折叠进来
- **writer** 只负责把已经展开好的内容写出去

---

### 2.3 比 record/payload 方案更自然

之前如果抽成：

- `payload`
- `records`
- `fields`

虽然更抽象，但和现有 general 层风格反而拉远了。

当前这版：

- `file.content`
- `file.tail`
- `file.attachments`

阅读上更直观，也更贴近“这个参数最终往哪个文件写出哪些行”。

---

## 3. 这一版的字段含义

### 3.1 `writerType`

当前仓库里注册的 writer 只有：

- `fixed_width`
- `csv`

所以从仓库现状出发，这里更适合继续沿用 `fixed_width`，而不是再起一个很强模型味道的新名字。

也就是说，这里的意思更接近：

- 仍然是固定宽度文本写入
- 只是写入粒度从“单字段”扩展成了“格式化行”

如果后面实现时要增强 `fixed_width`，也应优先往“更通用的固定宽度文本 writer”方向走，而不是发明一个 `swatplus_calibration_writer`。

---

### 3.2 `file.name`

目标文件名，例如：

```yaml
name: calibration.cal
```

---

### 3.3 `file.line`

主记录起始行号。

例如：

```yaml
line: 6
```

表示该参数的主记录写在第 6 行。

后面的：

- `tail`
- `attachments`

都依附于这一条主记录。

这里建议语义保持简单：

- `line` 只标记主记录行
- attachment 后续行由 writer 顺延

---

### 3.4 `file.content`

主记录主体。

结构：

```yaml
content:
  format:
  values:
```

其中：

- `format` 是这一整行主体部分的固定宽度格式
- `values` 是按位置填入的值

---

### 3.5 `file.tail`

主记录尾部附加内容。

这个位置主要用来承接：

- `OBJ_TOT`
- 后面跟的对象 id 列表

结构同样保持一致：

```yaml
tail:
  format:
  values:
```

如果没有尾部对象列表，建议直接不写 `tail`。

---

### 3.6 `file.attachments`

主记录后的附加行列表。

这里主要承接：

- `CONDS` 对应的若干条件行

结构：

```yaml
attachments:
  - format:
    values:
  - format:
    values:
```

如果没有附加行，建议直接不写 `attachments`。

---

### 3.7 `@value`

`@value` 表示运行时当前参数值占位符。

例如：

```yaml
values: [cn2, abschg, "@value", 1, 0, 0, 0, 0, 0, 0, 3]
```

表示第 3 个位置运行时填入当前参数值。

这个占位符是否最终保留成 `@value`，后面还可以再定，但它表达的能力是需要的。

---

## 4. 格式规则

这一点必须收紧。

### 4.1 每一个位置都要显式写格式

允许：

```yaml
format: "{0:<12}{1:<21}{2:>14.6f}{3:>9d}"
```

不建议：

```yaml
format: "{0:<12}{1:<21}{2}{3:>9}"
```

原因很简单：

- 这样更稳定
- 可读性更好
- 不会出现“默认格式到底是什么”的灰区

---

### 4.2 `values` 按位置写，不再带字段名

也就是：

```yaml
values: [cn2, abschg, "@value", 1, 0, 0, 0, 0, 0, 0, 3]
```

而不是：

```yaml
fields:
  NAME: cn2
  CHG_TYPE: abschg
```

因为到了 general 层，模板已经知道每一列该放什么，没必要再保留一层字段名映射。

---

## 5. 一个完整示例

这个例子表示：

- 参数 `cn2`
- `mode: a`
- 最终映射成 `abschg`
- 主记录有对象 id 尾部
- 后面跟 1 条条件行

```yaml
physical:
  - name: cn2
    type: float
    bounds: [-8, 8]
    mode: a
    writerType: fixed_width
    file:
      name: calibration.cal
      line: 6
      content:
        format: "{0:<12s}{1:<21s}{2:>14.6f}{3:>9d}{4:>8d}{5:>7d}{6:>8d}{7:>9d}{8:>8d}{9:>5d}{10:>7d}"
        values: [cn2, abschg, "@value", 1, 0, 0, 0, 0, 0, 0, 3]
      tail:
        format: "{0:>5d}{1:>5d}{2:>5d}"
        values: [12, 18, 21]
      attachments:
        - format: "{0:<12s}{1:<10s}{2:>8d}{3:>8d}"
          values: [cal_group, null, 0, 3]
```

这个例子里：

- `content` 最后一个 `3` 是 `OBJ_TOT`
- `tail` 里有 3 个对象 id
- `content` 里的 `1` 是 `CONDS`
- 所以后面跟 1 条 attachment

---

## 6. 一个最简单的例子

```yaml
physical:
  - name: esco
    type: float
    bounds: [0.1, 0.9]
    mode: v
    writerType: fixed_width
    file:
      name: calibration.cal
      line: 4
      content:
        format: "{0:<12s}{1:<21s}{2:>14.6f}{3:>9d}{4:>8d}{5:>7d}{6:>8d}{7:>9d}{8:>8d}{9:>5d}{10:>7d}"
        values: [esco, absval, "@value", 0, 0, 0, 0, 0, 0, 0, 0]
```

这表示：

- 没有条件行
- 没有对象 id 列表

---

## 7. 条件过滤示例

### 7.1 `landuse`

```yaml
physical:
  - name: esco
    type: float
    bounds: [0.1, 0.9]
    mode: v
    writerType: fixed_width
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

### 7.2 `hsg`

```yaml
physical:
  - name: perco
    type: float
    bounds: [-15, 15]
    mode: r
    writerType: fixed_width
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

### 7.3 `cal_group`

```yaml
physical:
  - name: cn2
    type: float
    bounds: [-8, 8]
    mode: a
    writerType: fixed_width
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

## 8. 如果模板层先做对象预筛选

比如用户层写的是：

- 指定 HRU id
- 或者按 slope 范围筛选 HRU

如果这些条件不直接落成 SWAT+ 原生 `condition line`，模板层也可以先把它解析成对象 id 列表，然后 general 层统一写成：

```yaml
physical:
  - name: cn2
    type: float
    bounds: [-8, 8]
    mode: a
    writerType: fixed_width
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

这样 writer 仍然不需要理解：

- HRU
- slope
- landuse
- cal_group

它只负责把格式化行写出去。

---

## 9. 这版设计和你刚才意见的对应关系

### 9.1 `mode` 不再和 `changeType` 并存

同意。

用户层继续保留：

- `mode: v`
- `mode: r`
- `mode: a`

模板层再把它映射成：

- `absval`
- `pctchg`
- `abschg`

这样和 SWAT2012 习惯更一致。

---

### 9.2 general 层不再拆字段名表

同意。

所以这里直接用：

```yaml
content:
  format:
  values:
```

而不是：

```yaml
content:
  fields:
```

---

### 9.3 `tail` 也必须完全格式化

同意。

所以 `tail` 和 `attachments` 一样，必须是：

```yaml
format:
values:
```

不能只保留一个裸数组。

---

### 9.4 每个位置都要显式格式

同意。

所以示例里全部改成了：

- `:<12s`
- `:>14.6f`
- `:>9d`

不再出现裸 `{2}` 这种写法。

---

## 10. 我现在的判断

如果目标是：

- 保持 `swatplus` 和 `swat2012` 风格尽量接近
- general 层不要再长出一套完全新的抽象
- writer 尽量保持通用，不带强模型标签

那这版已经比较顺。

下一步如果你认可这个方向，再往下就该定两件事：

1. `fixed_width` 是直接增强，还是新增一个更通用但不带模型味道的文本 writer
2. user 层 `filter` 怎么稳定映射到：
   - `attachments`
   - `tail`
   - 或模板层预筛选对象 id
