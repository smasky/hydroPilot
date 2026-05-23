# `formatted_text` General 层设计草案

这份文档只回答一个问题：

- 如果 `general` 层要支持一种新的通用 writer：`formatted_text`
- 那它本身应该怎么设计，才能不夹带模型私货

这里不讨论 `swatplus`、`xaj`、`swat2012` 的具体业务规则。

这里只讨论：

- general 层最小需要表达什么
- `ParamWritePlan` 只能理解什么
- writer 只能负责什么

---

## 1. 设计目标

`formatted_text`` 的定位应该很克制。

它不是：

- SWAT+ writer
- calibration writer
- 专门服务某一种模型的 writer

它应该只是一个通用能力：

- 根据若干格式化行描述
- 生成一个文本文件

也就是说，它解决的是这类问题：

- 某个模型输入文件不是“定点改已有字段”
- 而是“按模板组织若干行，再整文件写出”

---

## 2. 和现有 writer 的边界

当前可以把 3 类 writer 这样理解：

### 2.1 `fixed_width`

- 已有文本文件
- 已知 `line/start/width`
- 对指定位置做局部覆盖

### 2.2 `csv`

- 表格文件
- 按列或单元格组织写入

### 2.3 `formatted_text`

- 文本文件
- 按“行片段描述”组织写入
- 通常是整文件生成或整文件重写

所以它和 `fixed_width` 的差别不是“是不是固定宽度”，而是：

- `fixed_width` 是定位写
- `formatted_text` 是布局写

---

## 3. general 层应该保留什么

如果它要是通用的，我认为 general 层只应该保留这 3 类信息：

1. 文件名
2. 行模板
3. 运行时占位值

换句话说，general 层不应该出现：

- `calibration parameter count`
- `SWAT+ condition line`
- `OBJ_TOT`
- `HRU`
- `subbasin`

这些都属于模型模板层语义，不属于通用 writer 语义。

---

## 4. 参数级 general 形态

参数级仍然放在 `parameters.physical[*]` 下。

最小形态我建议还是：

```yaml
physical:
  - name:
    type:
    bounds:
    mode:
    writerType: formatted_text
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

这里面只有一个字段有点敏感，就是 `line`。

但它仍然是通用的，因为它表达的只是：

- 这条主记录在文件中的顺序位置

而不是某种模型业务含义。

---

## 5. `content / tail / attachments` 的通用理解

这里必须换成纯 writer 视角理解。

### 5.1 `content`

表示该参数对应的主记录行主体。

它只是：

- 一条格式字符串
- 一组待填充值

writer 不应该知道这行是不是：

- 参数主记录
- 控制记录
- 列名记录

在通用层，它只是一段主内容。

---

### 5.2 `tail`

表示与主记录同行拼接的附加片段。

它的通用含义只是：

- 主行末尾还有一段需要继续渲染的文本

writer 不应该知道它是不是：

- 对象 id 列表
- 注释
- 标记位

---

### 5.3 `attachments`

表示主记录之后紧跟的附加行。

它的通用含义只是：

- 这条参数记录除了主行外，后面还要多跟若干行

writer 不应该知道这些行是不是：

- 条件行
- 子记录
- 注释行

---

## 6. 文件级信息怎么处理

这里是最关键的边界。

如果 general 要通用，文件级信息不能写成：

- `calibrationHeader`
- `parameterCountLine`

这种带模型味道的名字。

更稳的通用理解应该是：

- 一个 `formatted_text` 文件除了参数记录外，还可能有固定前置行
- 某些前置行里，可能有聚合值占位符

也就是说，文件级能力本质上应该只有：

1. 前置行
2. 聚合占位符

但这部分不一定要进 YAML。

我更倾向它只存在于：

- builder 产出的内部元信息
- 或 `ParamWritePlan` 聚合后的内部 task 数据

而不是暴露成新的 general 配置块。

---

## 7. `ParamWritePlan` 应该只做什么

`ParamWritePlan` 如果要继续保持通用，就只能做 3 件事：

1. 按 `(fileName, writerType)` 聚合参数
2. 收集每条参数记录对应的行布局信息
3. 回填纯聚合值

这里所谓“纯聚合值”只能是这类东西：

- 本文件共有多少条记录
- 本文件里记录按什么顺序排

不能是：

- 这是 SWAT+
- 这是 calibration
- 第二行必须叫参数个数

后面这些都不应该由 `ParamWritePlan` 知道。

---

## 8. writer 应该只做什么

`formatted_text` writer 的职责应该极小：

1. 接收已经聚合好的文件描述
2. 渲染各行
3. 按顺序写出文本文件

它不负责：

- 业务字段翻译
- 参数筛选
- 记录数统计规则
- 模型对象语义

也就是说，writer 只负责：

```text
format + values -> text line
text lines -> file
```

---

## 9. 运行时占位符也要保持通用

像 `@value` 这样的占位符可以保留，但语义必须通用。

它应该表达成：

- 当前参数值

而不是：

- SWAT+ 参数值

如果后面还有别的占位符，也应尽量收敛成这类通用东西：

- `@value`
- `@index`
- `@recordCount`

这里的关键是：

- 名字表达的是数据来源类型
- 不是模型业务含义

---

## 10. 用 `swatplus calibration.cal` 验证这套抽象

如果这套抽象是通用的，那么 `swatplus` 只是一个实例：

- builder 负责把：
  - 参数名
  - mode
  - filter
  - 对象筛选
  - 条件翻译
  转成纯 `formatted_text` 描述

- 一旦进入 general / write plan / writer
  - 剩下的只是：
    - 前置行模板
    - 主记录
    - 行尾附加片段
    - 后续附加行

如果换另一个模型，只要它也符合“格式化行生成文本文件”这个模式，这套 `formatted_text` 也一样能用。

这才说明它不是 `swatplus` 私货。

---

## 11. 我现在建议的最终边界

### 11.1 模型层

模型层负责：

- 业务语义翻译
- 参数筛选翻译
- 模型字段映射

### 11.2 general 层

general 层负责：

- 通用 writer 描述

也就是只保留：

- `writerType`
- `file.name`
- `file.line`
- `content`
- `tail`
- `attachments`

### 11.3 `ParamWritePlan`

只负责：

- 聚合同文件参数记录
- 回填纯聚合占位值

### 11.4 `formatted_text` writer

只负责：

- 渲染
- 输出

---

## 12. 我现在的判断

如果按这个边界收口，那么：

- `formatted_text` 可以成立为一个真正的通用 writer
- `swatplus` 可以使用它
- 但不会把 `swatplus` 的业务逻辑灌进 general 核心

下一步如果继续细化，我建议只做两件事：

1. 定义 `formatted_text` 在 general 层的最小字段集
2. 定义哪些占位符算“通用占位符”

