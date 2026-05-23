# SWAT 2012 日尺度——分步指南

本指南带你完成 HydroPilot 与 SWAT 2012 工程的第一次对接。你会从一个普通的 TxtInOut 目录出发，走到一份经过校验、通过冒烟测试、可以直接用于后续标定的配置文件。

## 开始之前你需要什么

- 一个 **SWAT 2012 TxtInOut 工程目录** ——包含 `file.cio`、`fig.fig`、`*.sub`、`*.mgt`、`*.gw` 及其他 SWAT 输入文件的文件夹。这就是你平时用 SWAT Editor 打开的那个目录。
- **SWAT 2012 可执行文件**（Windows 上通常为 `swat.exe`，Linux + Wine 环境下为 `swat`）。
- **HydroPilot 已安装**——`pip install hydropilot`（需要 Python 3.10+）。

如果你手头还没有现成的 SWAT 工程，可以随便用一个合法的 SWAT 2012 TxtInOut 目录跟着走，步骤是一样的。

---

## 第一步：确定你的工程和可执行文件

HydroPilot 需要知道三件事：

| 设置 | 含义 | 示例 |
|---|---|---|
| `projectPath` | TxtInOut 目录的路径 | `E:\BMPs\TxtInOut` |
| `workPath` | HydroPilot 创建运行副本的位置 | `./work` |
| `command` | 模型可执行文件名 | `swat.exe` |

`projectPath` 和 `workPath` 都是相对于配置文件所在目录。如果你的配置文件在 `E:\myCalibration\my_config.yaml`，则 `./work` 对应 `E:\myCalibration\work`。

你也可以直接用绝对路径：

```yaml
basic:
  projectPath: E:\BMPs\TxtInOut
  workPath: E:\myCalibration\work
  command: swat.exe
```

**为什么重要：** HydroPilot 每次运行都会把你的 `projectPath` 复制到一个隔离的工作空间中，永远不会触及原始工程文件。模型在副本中运行，结果也落在工作空间里。

---

## 第二步：创建一份最小化的日尺度配置

新建一个 YAML 文件，起名叫 `my_first.yaml`。以 `version: swat` 开头。这会告诉 HydroPilot 使用 SWAT 2012 模板，由模板来帮你处理列位置和行计算。

### 完整的最小配置

```yaml
version: swat

basic:
  projectPath: E:\myProject\TxtInOut
  workPath: ./work
  command: swat.exe

parameters:
  design:
    - name: CN2
      bounds: [35, 98]
    - name: ALPHA_BF
      bounds: [0, 1]
    - name: GW_DELAY
      bounds: [0, 500]

series:
  - id: flow
    desc: 出口断面日流量
    sim:
      file: output.rch
      id: 33
      variable: FLOW_OUT
      period: [2010, 2015]
    obs:
      file: obs_flow.txt
      rowRanges:
        - [1, 2191]
      colNum: 1

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
    desc: 最大化 NSE
    ref: nse_flow
    sense: max
```

下面逐块解释。

### `basic`

```yaml
basic:
  projectPath: E:\myProject\TxtInOut
  workPath: ./work
  command: swat.exe
```

`projectPath` 指向你的 TxtInOut 目录。`workPath` 是运行时工作空间的存放位置。`command` 是 SWAT 2012 可执行文件——如果已经在系统 PATH 中，写 `swat.exe` 即可；否则用完整路径如 `C:\SWAT\swat.exe`。

### `parameters`——你要标定什么

```yaml
parameters:
  design:
    - name: CN2
      bounds: [35, 98]
    - name: ALPHA_BF
      bounds: [0, 1]
    - name: GW_DELAY
      bounds: [0, 500]
```

`design` 列出优化器将要调整的参数。每个参数需要一个名称和有效范围（`bounds`）。这三个参数（CN2、ALPHA_BF、GW_DELAY）是初次日尺度标定的常见起点。

因为当前处于 `version: swat` 模式，你不需要指定要修改哪些 SWAT 文件、写哪些列——模板会从内置的 SWAT 2012 数据库自动解析参数位置。

### `series`——模拟数据和观测数据

```yaml
series:
  - id: flow
    desc: 出口断面日流量
    sim:
      file: output.rch
      id: 33
      variable: FLOW_OUT
      period: [2010, 2015]
    obs:
      file: obs_flow.txt
      rowRanges:
        - [1, 2191]
      colNum: 1
```

- `id: flow`——你自己取的名字。HydroPilot 用它构成上下文键名，比如 `flow.sim` 和 `flow.obs`。
- `sim.file: output.rch`——包含目标变量的 SWAT 输出文件。河段/河道变量用 `output.rch`。
- `sim.id: 33`——你要读取的河段号（子流域出口）。在你的 SWAT 工程的 `fig.fig` 或流域设置中可以查到。
- `sim.variable: FLOW_OUT`——变量名。模板会从 SWAT 2012 数据库中查找 `output.rch` 中的正确列范围。
- `sim.period: [2010, 2015]`——标定年份。必须落在 SWAT 工程的模拟时段内（来自 `file.cio`）。
- `obs.file: obs_flow.txt`——你的观测流量数据文件，放在配置文件旁边。每行一个值，与时间步长匹配（日尺度）。
- `obs.rowRanges: [[1, 2191]]`——从观测文件中读取哪些行。2191 天 = 2010 到 2015 共 6 年。
- `obs.colNum: 1`——数据在哪一列。

模板会根据 `id`、`period` 和你的工程元数据（子流域数量、模拟起始日期）自动计算 `sim` 的行位置。

### `functions`、`derived`、`objectives`——评估

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
    desc: 最大化 NSE
    ref: nse_flow
    sense: max
```

- `functions` 声明你需要哪些评估函数。`NSE` 是内置的。
- `derived` 计算中间值。这里 `nse_flow` 用模拟和观测流量调用 `NSE`。
- `objectives` 告诉优化器目标是什么。`ref: nse_flow` 指向 derived 值。`sense: max` 表示 NSE 越大越好。

---

## 第三步：校验配置

运行校验器：

```bash
hydropilot-validate my_first.yaml
```

这会检查你的配置，但不会运行模型。对于 `version: swat` 配置，校验器会检查：

- `projectPath` 存在且包含必需的 SWAT 2012 文件（`file.cio`、`fig.fig`）
- 参数名称合法且没有歧义
- 每个序列的 `sim` 指定了合法的 SWAT 输出文件（`output.rch`、`output.sub` 或 `output.hru`）
- 每个 `sim` 声明了变量名（`variable`）或显式列位置（`colSpan`/`colNum`）
- 每个 `sim` 有子流域/河段 ID（`id`）或显式行选择
- 观测文件存在且可读
- 观测读取器提供了行和列选择器
- 标定时段落在工程模拟时段内

如果一切正常，你会看到：

```
Config is valid.
```

如果有错误，校验器会逐条打印，每条包含路径（如 `series[flow].obs`）和建议。逐一修复即可。

常见初次错误：
- `projectPath: directory not found`——检查路径。不确定就用绝对路径。
- `observation file not found`——确保 `obs_flow.txt` 和配置文件在同一目录下。
- `sim.id` 超出范围——你的工程可能没有那么多子流域。检查 `fig.fig`。

校验器不会运行模型。它只检查配置本身是否合理。

---

## 第四步：冒烟测试

校验通过后，跑冒烟测试：

```bash
hydropilot-test my_first.yaml
```

`hydropilot-test` 做了以下事情：
1. 加载你的配置并展开模板。
2. 在 `workPath` 中创建一个隔离的工程副本。
3. 应用一套默认参数向量（取每个参数边界的中点）。
4. 在副本中运行你的模型命令。
5. 用你定义的序列提取模拟输出。
6. 计算目标函数值（本例中是 NSE）。
7. 在运行存档下写入测试报告 `test-report.md`。

这能证明：

- 你的模型可执行文件可以正常运行。
- 参数到文件的接线是对的（HydroPilot 找到了正确的文件来修改）。
- 序列提取可以解析到实际的行和列。
- 目标函数能产出真实的数值。

冒烟测试不能证明：

- 你的参数边界适合标定。
- 多次运行不会互相干扰。
- 并行执行可行。
- 你的观测数据正确或对齐良好。

它是一次接线检查，不是标定。

---

## 第五步：检查展开后的 general 配置

`hydropilot-test` 成功后，看一下配置文件旁边。你会找到一个文件：

```
my_first_general.yaml
```

这就是运行时实际使用的、完全展开后的 `version: general` 配置。SWAT 2012 模板已解析好：

- `variable: FLOW_OUT` → 具体的 `colSpan: [52, 61]`
- `id: 33, period: [2010, 2015]` → 具体的 `rowRanges: [[...]]`
- 参数名（CN2、ALPHA_BF、GW_DELAY）→ 每个 SWAT 输入文件的具体 `file.name`、`line`、`start`、`width`、`precision`

在以下情况查看这个文件很有用：

- 你想确认模板把参数解析到了你预期的行和列。
- 你需要排查序列提取问题。
- 你准备从模板模式切换到 general 模式以获取完全控制权。

不用编辑这个文件——每次 HydroPilot 加载配置时它都会重新生成。要改就改你的 `version: swat` 配置。

---

## 第六步：接入你自己的观测文件

现在把 `obs_flow.txt` 替换成你自己的观测数据。

日尺度观测文件的要求：

- 每行一天，按时间顺序排列，与你的 `period` 起止日期匹配。
- 每行一个值（如果使用 `colNum`，则是每行特定列一个值）。
- 纯文本，无表头。

示例——如果标定时段是 2010–2015（2192 天），你的文件就需要 2192 行。数一下：

```bash
# Linux/Mac
wc -l obs_flow.txt

# Windows (PowerShell)
(Get-Content obs_flow.txt).Count
```

更新你的配置：

```yaml
series:
  - id: flow
    sim:
      file: output.rch
      id: 33
      variable: FLOW_OUT
      period: [2010, 2015]
    obs:
      file: my_observed_flow.txt
      rowRanges:
        - [1, 2192]
      colNum: 1
```

重新校验和测试：

```bash
hydropilot-validate my_first.yaml
hydropilot-test my_first.yaml
```

**注意：** 如果观测文件的行数和模拟时段不匹配，校验器会警告你，但测试可能仍会运行。不匹配通常意味着你的 `period`、时间步长或行数有误。在进入标定之前修正它。

---

## 第七步：调整第一个标定目标

有了可用的配置后，你现在可以选择标定目标了。

### 从单一目标开始

第一次真实标定，建议只设一个出口的一个目标。单目标设置更容易调试，运行也更快。

```yaml
objectives:
  - id: obj_nse
    desc: 出口 33 的 NSE
    ref: nse_flow
    sense: max
```

`derived` 块负责计算指标：

```yaml
derived:
  - id: nse_flow
    call:
      func: NSE
      args: [flow.sim, flow.obs]
```

### 选择合适的变量

`FLOW_OUT` 是好的首选，因为它受约束较强（子流域出口总出流必须匹配实测流量），也是最常见的观测数据。

如果以后想标定水质或其他变量，可以添加更多 `series` 条目，并用新的 `derived` + `objectives` 指向它们。但先从一项开始。

### 检查子流域范围

你的 `sim.id` 必须是工程中实际存在的河段 ID。查找有效 ID：

- 打开 TxtInOut 目录中的 `fig.fig`。第一行就是子流域数量。
- 子流域 ID 从 1 到子流域总数。
- 每个子流域有一个河段出口（对应 `output.rch` 的一行），所以河段 ID 等于子流域 ID。

如果你的配置写 `id: 33`，但工程只有 25 个子流域，校验时模板就会拒绝。

### 下一步做什么

当你的配置用你自己的观测数据通过了校验和冒烟测试后：

- 如果你有物理限制（如最小体积比），添加约束条件。
- 添加诊断项（RMSE、KGE）来跟踪，但不作为优化目标。
- 通过 Python API 接入批量运行或 UQPyL 优化。

---

## 常见新手错误

### `projectPath` 写错

```yaml
# 错误——这是配置文件自己的目录
basic:
  projectPath: ./
```

`projectPath` 必须指向你的 SWAT 2012 TxtInOut 目录，而不是配置文件所在目录。不确定就用绝对路径：

```yaml
basic:
  projectPath: E:\SWAT_Projects\MyWatershed\TxtInOut
```

### 可执行文件名或路径写错

如果模型可执行文件不在系统 PATH 中，请用完整路径：

```yaml
basic:
  command: C:\SWAT\SWAT_Edit\swat.exe
```

在 Linux + Wine 环境下，命令可能是：

```yaml
basic:
  command: wine swat.exe
```

### 观测数据行数不匹配

假设 `period` 是 `[2010, 2015]`，日尺度。那就是 6 年 × 365/366 天 ≈ 2192 天。如果你的观测文件只有 1800 行，结果会对不上。先数好行数，确保和时段对应。

日尺度数据中，闰年多一天。2012 年是闰年，所以 2010–2015（含首尾）共 2192 天（6 × 365 + 1）。

### `sim.id` 超出了发现的范围

模板会读取工程的 `fig.fig` 获取子流域数量。如果你在一个只有 33 个子流域的工程中指定 `id: 62`，校验会失败。先确认工程的子流域数量。

### 时间步长是推导的，不需要声明

SWAT 模板会根据工程的 `file.cio` 中的 IPRINT 设置自动推导时间步长。**不要**在 `sim` 块中声明 `timestep`——SWAT 校验器会拒绝：

```yaml
# 错误——SWAT 校验器会拒绝 sim.timestep：
sim:
  file: output.rch
  id: 33
  variable: FLOW_OUT
  period: [2010, 2015]
  timestep: monthly
```

如果需要不同的时间步长（例如从日尺度切换到月尺度），请在 SWAT 工程中修改 IPRINT 设置，重新运行 SWAT 生成新的输出文件。HydroPilot 在模板展开时从工程元数据中读取时间步长。

### 对 `obs.file` 路径的误解

观测文件是相对于配置文件解析的，不是相对于模型工程目录。如果你的配置在 `E:\myCalibration\config.yaml`，那么 `obs.file: obs_flow.txt` 对应的是 `E:\myCalibration\obs_flow.txt`。

```yaml
# 你的配置在：E:\myCalibration\my_config.yaml
# 以下 obs 文件的查找路径：E:\myCalibration\my_data\flow.txt
obs:
  file: my_data/flow.txt
```

---

## 另见

- [SWAT 2012 模板参考](../templates/swat-2012.md) — 完整模板功能和配置结构。
- [配置参考](../configuration-reference.md) — 所有 general 模式字段及默认值。
- [示例](../examples.md) — 所有示例配置及说明。
- [CLI 参考](../cli.md) — 全部四个 CLI 命令。
