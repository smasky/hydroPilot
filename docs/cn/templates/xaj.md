# XAJ 模板

`version: xaj` 是面向 **XAJ** 水文模型工程的模板。它将一份简洁的、懂 XAJ 的配置展开为标准 `version: general` 配置，底层使用 CSV 读取器和 CSV 写入器。

## 模板展开后是什么

| 方面 | 模板输入 | 展开后的 general 输出 |
|---|---|---|
| Writer 类型 | 隐式（模板内置 XAJ 知识） | `writerType: csv` |
| Reader 类型 | 隐式（模板内置 XAJ 知识） | `readerType: csv` |
| 参数位置 | 变量名 + 可选 RIVID 过滤 | `parameters.csv` 中的具体行/列位置 |
| 序列列定位 | `variable` + 可选 `rivid` | 从 CSV 输出表头解析出的 `colNum` |
| 行偏移 | `headSkip` | 叠加到所有 `rowRanges` / `rowList` 值 |

模板展开由 `XajTemplate.build_config()` 完成。运行时始终基于展开后的 `version: general` 配置执行。成功调用 `load_config()` 后，HydroPilot 会在源 YAML 旁边生成 `<stem>_general.yaml`，你可以直接查看展开结果。

## 工程布局

一个 XAJ 工程目录必须包含：

| 文件 | 用途 |
|---|---|
| `xaj.yaml` | 工程描述文件——声明输入、工况设置和参数文件路径 |
| `parameters.csv` | 参数表，含 `RIVID` 列和参数值列 |
| `streamflow.csv` | 模型输出（各河段径流） |
| `Runoff_Yield.csv` | 模型输出（各河段产流） |
| `ET.csv`、`WD.csv`、`WL.csv` | 可选输出文件（蒸散发、需水量、水位） |

`xaj.yaml` 描述文件在工程发现阶段被读取，但 HydroPilot 不会修改它。

## 配置结构

### `version`

```yaml
version: xaj
```

### `basic`

```yaml
basic:
  projectPath: "../xaj"
  workPath: "./work"
  command: "./pyxaj.exe run xaj.yaml"
```

### `parameters`

两层设计，与通用模式一致：

- `design` — 优化器看到的变量。
- `physical` — 变量如何映射到 `parameters.csv` 的行和列。

```yaml
parameters:
  design:
    - name: KC
      bounds: [0.5, 2.0]
    - name: WM
      bounds: [80, 200]

  physical:
    - name: KC
      mode: v
      filter:
        rivid: 60711600
    - name: WM
      mode: v
```

#### 基于 RIVID 的参数过滤

XAJ 模板支持在 physical 参数上使用 `rivid` 过滤。设置后，模板将参数定位到 `parameters.csv` 中 `RIVID` 列匹配的特定行：

```yaml
physical:
  - name: KC
    mode: v
    filter:
      rivid: 60711600       # 仅写入 RIVID 为 60711600 的行
```

不加 filter 时，参数写入 `parameters.csv` 中的所有数据行。

参数文件默认为 `parameters.csv`，除非 `xaj.yaml` 描述文件在 `inputs.parameters` 或 `case.parameter` 下指定了其他路径。

### `series`

XAJ 序列使用 `variable` 名称来识别输出文件和列位置：

```yaml
series:
  - id: flow
    desc: "XAJ 出口断面流量"
    sim:
      variable: Streamflow
      rowRanges:
        - [1, 1000]
    obs:
      file: "../xaj/streamflow.csv"
      rowRanges:
        - [2, 1001]
      colNum: 2
```

关键字段：

| 字段 | 用途 |
|---|---|
| `sim.variable` | 命名输出变量（`Streamflow`、`Runoff` 等）——自动解析为文件 + 列 |
| `sim.rivid` | 当输出 CSV 使用基于 RIVID 的列头时，用于确定读取哪一列 |
| `sim.file` | 覆盖自动解析的输出文件名 |
| `sim.headSkip` | 跳过的表头行数（默认取决于变量） |
| `sim.rowRanges` | 提取的行范围。设置 `headSkip` 后这些值会自动偏移 |
| `obs.file` | 观测 CSV 文件，相对于配置文件解析 |
| `obs.rowRanges` | 行范围，不会自动偏移 |

#### 基于变量的列解析

当你写 `variable: Streamflow` 而不指定 `colNum` 时，模板会：

1. 在 XAJ 变量数据库中查找该变量。
2. 解析出它属于哪个输出文件（`streamflow.csv`）。
3. 如果输出文件使用基于 RIVID 的列头，则用 `rivid` 找到正确的列。
4. 用 `headSkip` 偏移所有行位置。

```yaml
# 简洁写法，自动解析
sim:
  variable: Streamflow
  rivid: 60711600
  rowRanges:
    - [1, 1000]
```

#### 多序列示例

```yaml
series:
  - id: flow
    sim:
      variable: Streamflow
      rowRanges:
        - [1, 1000]
    obs:
      file: "../xaj/streamflow.csv"
      rowRanges:
        - [2, 1001]
      colNum: 2

  - id: runoff
    sim:
      variable: Runoff
      rivid: 60711600
      rowRanges:
        - [1, 1000]
```

没有显式 `obs` 的序列是可选的——该序列将只有模拟数据。

### `functions`、`derived`、`objectives`

结构与 general 模式相同：

```yaml
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

## 工程发现

模板加载时读取工程目录中的 `xaj.yaml`，找到参数文件路径。然后扫描 `parameters.csv` 以：

- 建立 `RIVID` → 数据行的索引（供参数过滤使用）。
- 记录所有数据行索引（供无过滤参数使用）。
- 扫描可用的输出 CSV（`streamflow.csv`、`Runoff_Yield.csv`、`ET.csv`、`WD.csv`、`WL.csv`）并缓存表头，供列解析使用。

## 参考示例

- `examples/test_xaj.yaml` — XAJ 单流域案例，使用 `rivid` 过滤的参数，含径流和产流序列。
- `examples/test_xaj_general.yaml` — `test_xaj.yaml` 展开后的 general 配置，展示解析后的 CSV 写入器行列。

## 适用范围

- 本模板适用于使用 `xaj.yaml` 作为工程描述文件、以 CSV 文件承载参数和输出的 XAJ 模型工程。
- 不覆盖非 CSV 格式的 XAJ 工作流。
- `version: xaj` 配置键与 `version: swat` 和 `version: general` 是互斥的。

## 与 SWAT 2012 模板的关键差异

XAJ 模板与 SWAT 2012 模板的底层机制不同：

| 维度 | SWAT 2012 (`version: swat`) | XAJ (`version: xaj`) |
|---|---|---|
| 参数文件格式 | 固定宽度文本文件（.mgt、.gw、.sol 等） | CSV 表格（`parameters.csv`） |
| Writer 类型 | `fixed_width` | `csv` |
| Reader 类型 | `text` | `csv` |
| 空间过滤字段 | `subbasin`、`land_use`、`soil`、`slope` | `rivid` |
| 工程描述文件 | 无额外描述文件（直接从 file.cio 等发现） | `xaj.yaml` |
| 输出文件 | `output.rch`、`output.sub`、`output.hru` | `streamflow.csv`、`Runoff_Yield.csv`、`ET.csv`、`WD.csv`、`WL.csv` |
| 时间步长来源 | 从 `file.cio` 的 IPRINT 自动推导 | 由 `xaj.yaml` 中的工况设置决定 |

`version: xaj` 和 `version: swat` 互斥——同一份配置不能同时使用两个模板。

## 另见

- [SWAT 2012 模板](swat-2012.md) — 另一个内置模板。
- [配置参考](../configuration-reference.md) — 所有 general 模式字段。
- [示例](../examples.md) — 完整示例说明。
