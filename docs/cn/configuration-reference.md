# 配置参考

本文档描述 `version: general` 配置模式。这是一个与模型无关的通用模式，所有模板配置（SWAT 2012、XAJ）在运行时会展开为此模式。

## 配置加载链路

```text
YAML 文件
  -> prepare_config()
     -> 解析 YAML
     -> 模板展开（若 version 不是 general）
     -> validate_general_config()
     -> RunConfig.from_raw()
  -> PreparedConfig
```

`load_config()` 包装了 `prepare_config()`，并额外在源 YAML 旁写入一份已解析的 `*_general.yaml` 文件，供人工检查。

校验分两层：结构检查先于 `RunConfig` 构造执行，随后 `RunConfig.from_raw()` 作为兜底捕获剩余问题。

## 顶层结构

一个 `version: general` 的 YAML 文件包含以下顶层键：

| 键 | 是否必需 | 类型 |
|---|---|---|
| `version` | 是 | `"general"` |
| `basic` | 是 | 映射 |
| `parameters` | 是 | 映射 |
| `series` | 是 | 非空列表 |
| `functions` | 否（默认 `[]`） | 列表 |
| `derived` | 否（默认 `[]`） | 列表 |
| `objectives` | 否（默认 `[]`） | 列表 |
| `constraints` | 否（默认 `[]`） | 列表 |
| `diagnostics` | 否（默认 `[]`） | 列表 |
| `reporter` | 否（默认 `{}`） | 映射 |

## `basic` — 项目路径、工作空间与执行命令

```yaml
basic:
  projectPath: E:\BMPs\TxtInOut
  workPath: ./work
  command: swat.exe
  timeout: -1
  parallel: 1
  keepInstances: false
```

| 字段 | 是否必需 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| `projectPath` | 是 | 路径 | — | 模型输入文件所在目录。每次运行实例会复制一份。 |
| `workPath` | 是 | 路径 | — | 运行实例及归档的工作目录。 |
| `command` | 是 | 字符串或列表 | — | 模型可执行命令。可以是单个字符串，也可以是参数列表。 |
| `timeout` | 否 | int | `-1` | 每次运行的超时秒数。`-1` 表示无超时。 |
| `parallel` | 否 | int | `1` | 并行工作线程数。每个线程拥有独立的项目副本。 |
| `keepInstances` | 否 | bool | `false` | 设为 `true` 时保留每次运行的实例目录，默认清理。 |

`projectPath` 和 `workPath` 相对于配置文件所在目录解析。

## `parameters` — 设计变量与物理参数映射

```yaml
parameters:
  design:
    - name: CN2
      type: float
      bounds: [35, 98]
    - name: ALPHA_BF
      type: float
      bounds: [0, 1]
  physical:
    - name: CN2
      type: float
      bounds: [35, 98]
      mode: v
      writerType: fixed_width
      file:
        name: '*.mgt'
        line: 11
        start: 1
        width: 16
        precision: 2
        maxNum: 1
    - name: ALPHA_BF
      type: float
      bounds: [0, 1]
      mode: v
      writerType: fixed_width
      file:
        name: '*.gw'
        line: 5
        start: 1
        width: 16
        precision: 4
        maxNum: 1
  hardBound: true
```

| 字段 | 是否必需 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| `design` | 是 | 非空列表 | — | 暴露给优化器的设计变量。 |
| `physical` | 是 | 非空列表 | — | 写入模型输入文件的物理参数。 |
| `hardBound` | 否 | bool | `true` | 若为 `true`，设计值在变换前会被限制在 `bounds` 范围内。 |
| `transformer` | 否 | 字符串或 null | `null` | 已注册的变换器名称，用于将设计空间映射到物理空间。 |

### 设计参数

`design` 列表中的每一项：

| 字段 | 是否必需 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| `name` | 是 | string | — | 参数名称。 |
| `type` | 否 | `"float"`、`"int"`、`"discrete"` | `"float"` | 变量类型。 |
| `bounds` | 否 | `[下界, 上界]` | `[0, 1]` | 允许的取值范围。 |
| `sets` | 否 | list | `[]` | 离散值集合（用于 `"discrete"` 类型）。 |

### 物理参数

`physical` 列表中的每一项：

| 字段 | 是否必需 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| `name` | 是 | string | — | 参数名称。 |
| `type` | 否 | `"float"`、`"int"` | `"float"` | 值类型。 |
| `bounds` | 否 | `[下界, 上界]` | `[0, 1]` | 允许的取值范围。 |
| `mode` | 否 | `"r"`、`"v"`、`"a"` | `"v"` | 写入模式：相对（r）、值（v）、绝对（a）。 |
| `writerType` | 否 | `"fixed_width"`、`"csv"` | `"fixed_width"` | 写入器类型。 |
| `file` | 是 | 映射 | — | 目标文件与写入位置（字段因写入器类型而异）。 |
| `sets` | 否 | list | `[]` | 离散值集合。 |

如果 `design` 与 `physical` 列表长度不同，则必须提供 `transformer`。

### 变换器

当指定 `transformer` 时，该字段引用一个函数，该函数接受设计向量 `X` 并返回物理向量 `P`。未指定变换器时，设计与物理参数按位置一一对应。

## `series` — 模拟结果与观测数据提取

```yaml
series:
  - id: flow
    desc: 月径流
    sim:
      readerType: text
      file: output.rch
      rowRanges:
        - [71, 753, 62]
      colSpan: [50, 61]
    obs:
      readerType: text
      file: obs_flow_monthly.txt
      rowRanges:
        - [1, 36]
      colSpan: [1, 12]
```

| 字段 | 是否必需 | 类型 | 说明 |
|---|---|---|---|
| `id` | 是 | string | 唯一序列标识。用于上下文键，如 `flow.sim` 和 `flow.obs`。 |
| `desc` | 否 | string | 可读的描述文本。 |
| `sim` | 是 | 映射 | 模拟提取：读取器或调用节点。 |
| `obs` | 否 | 映射或 null | 观测提取：仅支持读取器。 |

### `sim` — 模拟数据

`sim` 块必须声明 `readerType` 或 `call` 之一，不可同时使用：

**读取器** — 从模型输出文件中提取数据：

```yaml
sim:
  readerType: text
  file: output.rch
  rowRanges:
    - [1, 365]
  colNum: 2
```

**调用** — 由函数从其他序列派生模拟数据：

```yaml
sim:
  call:
    func: sum_series
    args: [flow.sim, runoff.sim]
```

### `obs` — 观测数据

`obs` 块仅接受读取器（不支持 `call`）：

```yaml
obs:
  readerType: text
  file: obs_flow_monthly.txt
  rowRanges:
    - [1, 36]
  colNum: 1
```

观测文件相对于配置文件所在目录解析。

### 读取器字段

所有读取器类型共有的字段：

| 字段 | 是否必需 | 类型 | 说明 |
|---|---|---|---|
| `readerType` | 是 | `"text"` 或 `"csv"` | 读取器类型。 |
| `file` | 是 | 路径 | 要读取的文件。`sim` 的路径相对于运行时工作目录解析；`obs` 的路径相对于配置文件解析。 |

其他字段取决于读取器类型（参见[读取器与写入器类型](#读取器与写入器类型)）。

## `functions` — 评估函数

```yaml
functions:
  - name: NSE
    kind: builtin
  - name: my_custom
    kind: external
    file: ./my_func.py
```

| 字段 | 是否必需 | 类型 | 说明 |
|---|---|---|---|
| `name` | 是 | string | 唯一的函数名称。 |
| `kind` | 是 | `"builtin"` 或 `"external"` | 函数来源。 |
| `args` | 否 | 字符串列表 | 在派生参数之前传入的额外位置参数。 |
| `file` | 否 | 路径 | `kind: external` 时的 Python 文件路径。该项为必填。 |

内置函数不需要 `file`。当前内置函数集合包括：`NSE`、`KGE`、`R2`、`RMSE`、`MSE`、`PBIAS`、`LogNSE`、`sum_series`。

## `derived` — 计算中间值

```yaml
derived:
  - id: nse_flow
    call:
      func: NSE
      args: [flow.sim, flow.obs]
```

| 字段 | 是否必需 | 类型 | 说明 |
|---|---|---|---|
| `id` | 是 | string | 唯一的派生值标识。 |
| `desc` | 否 | string | 可读的描述文本。 |
| `call.func` | 是 | string | 函数名称（必须匹配已定义的函数）。 |
| `call.args` | 是 | 字符串列表 | 参数，通常为上下文引用，如 `flow.sim`。 |

派生值会以其 `id` 出现在运行时上下文中，可被目标、约束、诊断或其他派生值引用。

## `objectives` — 优化目标

```yaml
objectives:
  - id: obj_nse
    desc: 最大化 NSE
    ref: nse_flow
    sense: max
```

| 字段 | 是否必需 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| `id` | 是 | string | — | 唯一目标标识。 |
| `desc` | 否 | string | — | 可读的描述文本。 |
| `ref` | 是 | string | — | 上下文引用（通常为派生值的 `id`）。 |
| `sense` | 否 | `"min"` 或 `"max"` | `"min"` | 优化方向。 |
| `on_error` | 否 | float | 自动 | 出错时的兜底值（参见错误语义说明）。 |

默认 `on_error`：`sense: max` 时为 `-inf`，`sense: min` 时为 `+inf`。

## `constraints` — 评估约束

```yaml
constraints:
  - id: con_volume
    ref: vol_ratio
```

| 字段 | 是否必需 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| `id` | 是 | string | — | 唯一约束标识。 |
| `desc` | 否 | string | — | 可读的描述文本。 |
| `ref` | 是 | string | — | 上下文引用。 |
| `on_error` | 否 | float | `+inf` | 出错时的兜底值。 |

## `diagnostics` — 信息性指标

```yaml
diagnostics:
  - id: diag_rmse
    name: RMSE 诊断
    ref: rmse_flow
```

| 字段 | 是否必需 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| `id` | 是 | string | — | 唯一诊断标识。 |
| `name` | 否 | string | — | 显示名称。 |
| `ref` | 是 | string | — | 上下文引用。 |
| `on_error` | 否 | float | `NaN` | 出错时的兜底值。 |

诊断属于警告性质。某个诊断失败不会使当次运行无效。

## `reporter` — 输出持久化

```yaml
reporter:
  flushInterval: 50
  holdingPenLimit: 20
  series: []
```

| 字段 | 是否必需 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| `flushInterval` | 否 | int | `50` | 每 N 次运行将记录刷新到磁盘。 |
| `holdingPenLimit` | 否 | int | `20` | 触发强制刷新前可持有的最大记录数。 |
| `series` | 否 | 字符串列表 | `[]` | 需要导出为逐次运行 CSV 的序列 `id` 列表。 |

`archive/` 目录下的输出产物：

- `results.db` — 包含所有运行记录的 SQLite 数据库
- `summary.csv` — 目标与约束的 CSV 汇总
- `error.jsonl` — 结构化的错误条目
- `error.log` — 纯文本错误日志
- `reporter.series` 中列出的每个序列 `id` 对应的逐次运行 CSV 文件

## 路径语义

### 配置文件路径解析

- `basic.projectPath` — 相对于配置文件所在目录解析。必须是一个存在的目录。
- `basic.workPath` — 相对于配置文件所在目录解析。

### 观测文件

`obs.file` 相对于**配置文件所在目录**解析。示例：

```yaml
# config.yaml 位于 ./project/config.yaml
# 观测文件位于 ./project/obs_flow.txt
obs:
  file: obs_flow.txt
```

### 模拟输出文件

`sim.file` 相对于**运行时工作目录**（即运行实例中的项目副本）解析。模型在其工作副本中生成输出文件，因此路径应相对于该位置：

```yaml
sim:
  file: output.rch
```

切勿对 `sim.file` 使用相对于 YAML 文件位置的路径。

## 错误与 on_error 语义

### 错误类型

运行时错误分为两个严重级别：

- `fatal`（致命）— 运行无法产生有效结果，将应用兜底值。
- `warning`（警告）— 错误被记录，但运行继续。

### 派生值的依赖关系

被目标或约束引用的派生值是**致命**依赖。如果其计算失败，运行将获得兜底值。

仅被诊断引用的派生值是**警告**依赖。失败时产生警告和 `NaN`，不会使运行无效。

### 默认兜底值

| 块 | 方向 | 默认 `on_error` |
|---|---|---|
| 目标 | `sense: min` | `+inf` |
| 目标 | `sense: max` | `-inf` |
| 约束 | — | `+inf` |
| 诊断 | — | `NaN` |

所有兜底值都可以用显式的 `on_error` 字段覆盖。

## 读取器与写入器类型

### 读取器

| 类型 | 说明 |
|---|---|
| `text` | 固定宽度或空格分隔的文本文件。支持 `rowRanges`、`rowList`、`colSpan`、`colNum`。 |
| `csv` | CSV 文件。支持 `rowRanges`、`rowList`、`colNum`、`delimiter`。 |

**Text 读取器字段：**

| 字段 | 是否必需 | 说明 |
|---|---|---|
| `file` | 是 | 文件路径。 |
| `rowRanges` 或 `rowList` | 是* | 行选择。 |
| `colSpan` 或 `colNum` | 是* | 列选择。 |

\* 必须恰好提供一个行选择器和一个列选择器。

`rowRanges` 格式：`[起始, 结束]` 或 `[起始, 结束, 步长]`。1 起始，含两端。

### 写入器

| 类型 | 说明 |
|---|---|
| `fixed_width` | 将值写入文本文件的固定宽度位置。`file.name` 支持 glob 模式。 |
| `csv` | 将值写入 CSV 单元格。 |

**Fixed-width 写入器 `file` 字段：**

| 字段 | 是否必需 | 说明 |
|---|---|---|
| `name` | 是 | 目标文件名或 glob 模式。 |
| `line` | 是 | 行号（1 起始）。 |
| `start` | 是 | 起始列位置（1 起始）。 |
| `width` | 是 | 字段宽度（字符数）。 |
| `precision` | 否 | 浮点数格式化的小数位数。 |
| `maxNum` | 否 | 从 `start` 起扫描的连续字段个数。 |
| `selectIndex` | 否 | 当设置了 `maxNum` 时，仅选取第 N 个扫描到的条目（1 起始）。省略时写入所有扫描到的条目。 |

**CSV 写入器 `file` 字段：**

| 字段 | 是否必需 | 说明 |
|---|---|---|
| `name` | 是 | 目标文件名。 |
| `rowList` 或 `rowRanges` | 是 | 行选择。 |
| `colNum` | 是 | 列号（1 起始）。 |
| `delimiter` | 否 | 字段分隔符（默认 `,`）。 |
| `precision` | 否 | 浮点数格式化的小数位数。 |

## 上下文引用

运行时上下文使用以点分隔的键：

- `X` — 输入设计向量
- `i` — 批次内的运行序号
- `P` — 解析后的物理参数向量
- `<series_id>.sim` — 提取的模拟数据（如 `flow.sim`）
- `<series_id>.obs` — 加载的观测数据（如 `flow.obs`）
- `<derived_id>` — 计算得到的派生值（如 `nse_flow`）

这些键用于 `call.args`、`derived.call.args` 以及 `ref` 字段。

## 最小示例

```yaml
version: general

basic:
  projectPath: ./project
  workPath: ./work
  command: my_model.exe

parameters:
  design:
    - name: K
      bounds: [0, 1]
  physical:
    - name: K
      mode: v
      writerType: fixed_width
      file:
        name: model.inp
        line: 12
        start: 1
        width: 10
        precision: 4

series:
  - id: flow
    sim:
      readerType: text
      file: model.out
      rowRanges:
        - [1, 365]
      colNum: 2
    obs:
      readerType: text
      file: obs_flow.txt
      rowRanges:
        - [1, 365]
      colNum: 2

functions:
  - name: NSE
    kind: builtin

derived:
  - id: nse_flow
    call:
      func: NSE
      args: [flow.sim, flow.obs]

objectives:
  - id: obj_nse
    ref: nse_flow
    sense: max
```
