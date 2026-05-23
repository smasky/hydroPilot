# 从日尺度迁移到月尺度 SWAT 2012 输出

本指南假设你已经在 HydroPilot 中有了一个正常工作的日尺度 SWAT 2012 配置，现在想切换到月尺度输出。本文解释什么会变，什么在沿用日尺度假设时会出错，以及如何避免常见错误。

## 什么时候从日尺度切换到月尺度

以下情况切换到月尺度：

- 你的标定目标是月尺度观测数据（在水质、水库调度或长周期研究中常见）。
- 你的观测数据只有月分辨率。
- 你想减少运行时间——月尺度输出每年只有 12 行数据，而日尺度有 365 或 366 行。
- 你的 SWAT 工程 IPRINT 已经设为 0（月尺度）。IPRINT 在 `file.cio` 第 59 行：`0` = 月尺度，`1` = 日尺度，`2` = 年尺度。

如果你的 SWAT 工程 IPRINT 是 1（日尺度），你必须先把它改成 0，并重新运行 SWAT 模拟，然后才能在 HydroPilot 中使用月尺度提取。HydroPilot 会根据工程的 IPRINT 设置自动推导时间步长——你不需要在配置中设置它。

## 和日尺度配置相比，什么会改变

和日尺度相比，你的配置只需要改两处（时间步长自动处理）：

### 1. 时间步长由工程推导

**不要**在 sim 块中设置 `timestep`。对于 SWAT 2012 配置（`version: swat`），校验器会拒绝 `sim.timestep`，因为时间步长根据工程 `file.cio` 中的 IPRINT 推导：

- IPRINT = 0 → 月尺度
- IPRINT = 1 → 日尺度
- IPRINT = 2 → 年尺度

模板在工程发现阶段读取 IPRINT，据此计算输出行数。同样的配置结构对日尺度和月尺度都有效——只有 SWAT 工程的 IPRINT 值决定时间步长。

如果你的工程 IPRINT 是 1（日尺度），模板会按日尺度计算行偏移（每个子流域每年 365/366 行）。把 IPRINT 改成 0 并重新运行 SWAT 即可生成月尺度输出。

### 2. period 的含义

和日尺度相比，同样的 `period: [2019, 2021]` 含义不同：

| Period | 日尺度行数 | 月尺度行数 |
|--------|-----------|-----------|
| `[2019, 2021]` | 3 年 × 365/366 ≈ 每个子流域 1,096 行 | 3 年 × 12 = 每个子流域 36 行 |

模板对不同时间步长采用不同的行数计算方式。详见[时段格式](#时段格式)。

### 3. 观测文件

你的观测文件必须包含月值，而不是日值：

```yaml
# 日尺度
obs:
  file: obs_flow.txt         # 2,191 个日值
  rowRanges:
    - [1, 2191]

# 月尺度
obs:
  file: obs_flow_monthly.txt  # 36 个月值
  rowRanges:
    - [1, 36]
```

观测行数必须等于你时段中的月份数：每年 12 行 × 年数。`[2019, 2021]`（3 年）预期 36 行。

## 为什么月尺度 SWAT 输出更棘手

月尺度 SWAT 输出有两个日尺度输出不存在的坑。

### 年均值行（MON=13）

SWAT 输出文件在每年 12 个月行之后会追加一行：MON=13，即年均值。这一行存在于每个 `output.rch`、`output.sub` 和 `output.hru` 文件中。

和日尺度不同（日尺度每行都是数据行），月尺度每年每个空间单元有 13 行——但你只需要 12 行。

模板通过计算不连续的 `rowRanges` 来处理这个问题。对于一个有 62 个子流域的工程，读取子流域 62，月尺度行模式为：

```
2019 年:
  MON=1, 子流域 1: 文件第 10 行
  ...
  MON=1, 子流域 62: 文件第 71 行
  MON=2, 子流域 62: 文件第 133 行
  ...
  MON=12, 子流域 62: 文件第 753 行
  MON=13 (年均值), 子流域 62: 第 815 行   ← 跳过

2020 年:
  MON=1, 子流域 62: 文件第 877 行
  ...
```

展开后的 general 配置中得到的 `rowRanges` 会自动跳过 MON=13 行：

```yaml
rowRanges:
  - [71, 753, 62]     # 2019 年：第 71, 133, 195, ..., 753 行（12 行，步长=62）
  - [877, 1559, 62]   # 2020 年：第 877, 939, ..., 1559 行（12 行，步长=62）
  - [1683, 2365, 62]  # 2021 年：第 1683, ..., 2365 行（12 行，步长=62）
```

每个区间每年跳过 12 × 62 = 744 行，年与年之间留有 62 行（MON=13 × n_subbasins）的间隙。三段式 `[start, end, step]` 格式告诉读取器："从 start 到 end，每 62 行读一行"。

### 为什么在 general 模式配置中会看到这些

在模板模式配置（`version: swat`）中，你只需要写 `id: 62` 和 `period: [2019, 2021]`。模板会为你计算不连续的 `rowRanges`。这正是月尺度工作推荐使用 `version: swat` 的主要原因——手工计算这些行极易出错。

如果你查看展开后的 `_general.yaml`，会看到多段 `rowRanges`。这是正确的，符合预期。不要试图把它们合并成一段连续区间——那样会把 MON=13 行也包含进来，导致提取结果错误。

## 实操：从日尺度到月尺度

以一份正常工作的日尺度配置为起点：

```yaml
version: swat

basic:
  projectPath: "E:\\BMPs\\TxtInOut"
  workPath: "./work"
  command: "swat.exe"

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
    desc: "出口断面日流量"
    sim:
      file: output.rch
      id: 62
      period: [2019, 2021]
    obs:
      file: obs_flow.txt
      rowRanges:
        - [1, 1095]
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
    desc: "最大化 NSE"
    ref: nse_flow
    sense: max
```

要转换成月尺度，做三处修改（时间步长由工程的 IPRINT 设置自动推导——不要在配置中添加）：

### 步骤 1：切换到月尺度观测文件

```yaml
obs:
  file: obs_flow_monthly.txt   # ← 改了
  rowRanges:
    - [1, 36]                  # ← 3 年 × 12 月 = 36
  colSpan: [1, 12]             # ← 可选，取决于观测文件格式
```

### 步骤 2：更新序列描述

```yaml
desc: "出口断面月流量"   # ← 更新以明确含义
```

### 步骤 3：校验和测试

```bash
hydropilot-validate config_monthly.yaml
hydropilot-test config_monthly.yaml
```

和日尺度相比，完整的月尺度配置（`examples/test_monthly.yaml`）在结构上完全相同——只有观测文件、行数和描述变了。时间步长由工程的 IPRINT 设置决定，不需要在配置中设置。

## 时段格式

月尺度提取支持三级时段精度。

### 年级精度

```yaml
period: [2019, 2021]
```

区间内每年的全部 12 个月。起点：第一年 1 月 1 日。终点：最后一年 12 月 31 日。这是最常用的形式。

### 月级精度

```yaml
period: ["2019-02", "2021-11"]
```

部分年份。起点：2019 年 2 月。终点：2021 年 11 月。适用于避开预热期或对齐不是从 1 月开始的观测窗口。

和日尺度相比，月级精度的工作方式相同——模板自动裁剪到月边界。

### 日期精度（裁剪到月边界）

```yaml
period: ["2019-02-03", "2021-11-01"]
```

对月尺度来说，精确日期不生效，时段按月边界裁切：2019 年 2 月到 2021 年 11 月。因此 `["2019-02-03", "2021-11-01"]` 和 `["2019-02-01", "2021-11-30"]` 在月尺度下产生相同的结果。

`test_monthly_series.yaml` 示例就展示了这一点：两个 sim 块分别用月级精度和日期级精度读取同一个子流域，`series_equal` 诊断项确认它们产生完全相同的序列。

### 多段时段

```yaml
period:
  - [2019, 2019]
  - [2021, 2021]
```

只提取 2019 和 2021 年，跳过 2020 年。每段是一个 `[start, end]` 对。当你需要在非连续年份上标定，或想排除已知异常年份时很有用。

## 多序列和警告

月尺度示例中包含两个进阶场景。

### 多序列提取（`test_monthly_series.yaml`）

从同一个 SWAT 输出文件中提取两个序列，各自使用不同的时段格式：

```yaml
series:
  - id: flow_month
    sim:
      file: output.rch
      variable: FLOW_OUT
      id: 62
      period: ["2019-02", "2021-11"]

  - id: flow_date
    sim:
      file: output.rch
      variable: FLOW_OUT
      id: 62
      period: ["2019-02-03", "2021-11-01"]
```

两个序列都从子流域 62 提取 `FLOW_OUT`。在月尺度下不同的时段格式产生相同结果，由 `series_equal` derived 函数验证。

这个示例还展示了派生序列：`flow_times_two` 接收 `flow_month.sim`，返回变换后的序列作为诊断项。

### call-type sim 和警告（`test_monthly_series_warning.yaml`）

第二个序列使用 `sim.call` 而非 `sim.file`：

```yaml
series:
  - id: flow_matrix
    sim:
      call:
        func: flow_as_matrix
        args: [flow_month.sim]
```

`sim.call` 从另一个序列计算生成序列，而非从文件读取。函数 `flow_as_matrix` 通过把月序列与自身堆叠，返回二维（矩阵形状）数组。

因为下游的目标函数和诊断项都期待一维序列，矩阵形状的派生序列会触发运行时警告。这是预期行为——该配置刻意设计来演示警告的传播。在生产配置中，确保派生序列返回一维数组。

reporter 的 `flushInterval` 设为 1 以立即呈现警告：

```yaml
reporter:
  flushInterval: 1
```

## 常见月尺度错误

### 1. 月尺度观测数据行数不匹配

最常见的错误：在月尺度提取中使用日尺度的观测行数。

```yaml
# 错误——1,095 行但只有 36 个月值
obs:
  rowRanges:
    - [1, 1095]
```

3 年月数据：3 × 12 = 36 行。5 年：60 行。仔细数好你的观测数据行数。

### 2. 对 period 边界含义理解错误

period 边界包含两端。`[2019, 2021]` 包含 2019、2020、2021 全部——是 3 年，不是 2 年。和日尺度不同（日尺度 3 年数据体感很多），月尺度 3 年输出只有 36 行——这是一个很小的标定数据集。

### 3. 假设月尺度行是连续的

在展开后的 general 配置中，`rowRanges` 是多段的。这是正确的——MON=13 行产生了间隙。如果你在 general 模式配置中手工写 `rowRanges`，请使用多段格式：

```yaml
# 错误——连续区间包含了 MON=13 行
rowRanges:
  - [71, 2365]

# 正确——多段，跳过 MON=13
rowRanges:
  - [71, 753, 62]
  - [877, 1559, 62]
  - [1683, 2365, 62]
```

### 4. 用日尺度假设做月尺度提取

- 日尺度：每个子流域每年 365 或 366 行。
- 月尺度：每个子流域每年 12 行。

不要试图用日行数除以 30 来估算月位置。模板根据 SWAT 工程结构计算月行——交给它处理。

### 5. 忘记匹配 IPRINT

SWAT 工程的 `file.cio` 第 59 行（IPRINT）决定输出时间步长：`0` = 月尺度，`1` = 日尺度，`2` = 年尺度。HydroPilot 根据该值自动推导时间步长。如果 IPRINT 是 1（日尺度），月尺度配置会算出错误的行位置。在使用月尺度提取之前，检查 `file.cio`，并将 IPRINT 改为 0 重新运行 SWAT。

### 6. 以为时间步长在配置中设置

对于 SWAT 2012 配置（`version: swat`），不要在 sim 块中写 `timestep`。校验器会拒绝它（时间步长从工程元数据推导）。同样的配置结构日尺度和月尺度通用——在 SWAT 工程中改 IPRINT，不要改 HydroPilot 配置。

## 另见

- [SWAT 2012 模板](../templates/swat-2012.md) — 模板参考和配置结构。
- [示例](../examples.md) — 所有示例配置及前置条件。
- [CLI 参考](../cli.md) — `hydropilot-validate` 和 `hydropilot-test` 用法。
