# SWAT 2012 参数与序列——决策指南

本指南帮助你在首次日尺度运行成功后，对 SWAT 2012 配置做出实用决策。涵盖输出文件选择、变量表达方式、时段与时间步长选择、参数写入策略和 HRU 过滤。建议与 [SWAT 2012 模板参考](../templates/swat-2012.md) 和[配置参考](../configuration-reference.md) 配合使用。

## 1. 选择输出文件

SWAT 2012 生成三种 HydroPilot 可以读取的输出文件。选择与你要评估的空间尺度匹配的那个。

### `output.rch`——河段级

每行是一个河段（子流域出口）在一个时间步长内的值。`sim.id` 是子流域 ID。

```yaml
series:
  - id: flow
    sim:
      file: output.rch
      id: 62               # 子流域 62
      period: [2019, 2021]
      variable: FLOW_OUT
```

**适用场景：** 子流域出口的径流标定。这是最常用的选择。

### `output.sub`——子流域级

每行是一个子流域在一个时间步长内的值。`sim.id` 是子流域 ID。包含子流域汇总变量（产水量、泥沙、营养盐负荷）。

```yaml
sim:
  file: output.sub
  id: 1
  period: [2010, 2015]
  variable: WYLD
```

**适用场景：** 子流域级汇总变量，如产水量或泥沙负荷。

### `output.hru`——HRU 级

每行是一个 HRU 在一个时间步长内的值。`sim.id` 是**全局** HRU 索引（从 1 开始，跨所有子流域顺序编号）。不是子流域内的局部 HRU 编号。

```yaml
sim:
  file: output.hru
  id: 15               # 全局 HRU 索引
  period: [2010, 2015]
  colSpan: [5, 16]
```

**适用场景：** HRU 级变量（蒸散发、土壤水、下渗）。根据工程的子流域布局确认全局 HRU 索引——子流域 1 的 HRU 排在最前面，然后是子流域 2 的，以此类推。

### 快速对比

| 输出文件 | `sim.id` 含义 | 典型用途 |
|---|---|---|
| `output.rch` | 子流域 ID（从 1 开始） | 出口断面流量 |
| `output.sub` | 子流域 ID（从 1 开始） | 子流域级水量/泥沙/营养盐 |
| `output.hru` | 全局 HRU 索引（从 1 开始） | HRU 级土壤/蒸散发变量 |

## 2. 选择变量表达方式

你可以用两种方式标识 SWAT 输出列。

### `variable`——基于名称查找

```yaml
sim:
  file: output.rch
  id: 62
  period: [2019, 2021]
  variable: FLOW_OUT
```

模板从 SWAT 变量数据库（`swat_db.yaml`）把 `FLOW_OUT` 解析为正确的 `colSpan`。这是推荐做法：你不需要记 SWAT 输出列的位置。

各文件可用变量：

| 文件 | 常用变量 |
|---|---|
| `output.rch` | `FLOW_IN`、`FLOW_OUT`、`SED_OUT`、`ORGN_OUT`、`ORGP_OUT`、`NO3_OUT`、`NH4_OUT`、`NO2_OUT`、`TN_OUT`、`TP_OUT` |
| `output.sub` | `PREC`、`SNOMELT`、`PET`、`ET`、`SW`、`PERC`、`SURQ`、`GW_Q`、`WYLD`、`SYLD`、`ORGN`、`ORGP`、`NSURQ`、`SOLP`、`SEDP` |
| `output.hru` | `PREC`、`SNOMELT`、`PET`、`ET`、`SW_INIT`、`SW_END`、`PERC`、`GW_RCHG`、`SURQ_GEN`、`GW_Q`、`WYLD`、`SYLD`、`ORGN`、`ORGP` |

注意：`output.sub` 中的变量 `PREC` 在 `swat_db.yaml` 中对应名称为 `PRECIP`，但 SWAT 官方文档中常简写为 `PREC`。以 `swat_db.yaml` 中的名称为准。

### `colSpan`——显式列范围

```yaml
sim:
  file: output.rch
  id: 62
  period: [2019, 2021]
  colSpan: [50, 61]
```

**优先使用 `colSpan` 的情况：**
- 你确切知道列位置，想锁定它们。
- 你要读取的变量不在 SWAT 数据库中。
- 你在调试，想绕过自动解析。

**优先使用 `variable` 的情况：**
- 你想让模板替你解析列位置。
- 你写的配置希望复用到其他 SWAT 2012 工程。
- `colSpan` 会随 SWAT 输出配置（IPRINT、ICALEN）变化，你想让模板处理这点。

大多数情况下，先试 `variable`。需要精确控制或变量不在数据库中时再切换到显式 `colSpan`。

## 3. 理解 `period` 和时间步长

### 时间步长由工程推导

SWAT 模板会在工程发现阶段从 `file.cio` 读取 IPRINT 设置，自动推导时间步长。你**不需要**在 `sim` 块中写 `timestep`——校验器会拒绝它。

| IPRINT 值 | 推导的时间步长 | 每个子流域每年行数 |
|---|---|---|
| 0 | 月尺度 | 12（仅 1-12 月；年均值行 MON=13 跳过） |
| 1 | 日尺度 | 365 或 366 |
| 2 | 年尺度 | 1 |

如果要改变提取的时间步长，请在 SWAT 工程中修改 IPRINT 并重新运行 SWAT 以生成对应频率的输出文件。HydroPilot 配置本身不控制时间步长。

### `period`

提取的时间窗口。格式从简到精：

```yaml
# 仅指定年份——最常用
period: [2019, 2021]

# 月级精度
period: ["2019-06", "2021-09"]

# 日期精度
period: ["2019-02-03", "2021-11-01"]

# 多段——非连续窗口
period: [[2019, 2019], [2021, 2021]]
```

**决策规则：**
- 除非需要截掉部分年份，否则用年级精度。
- 想避免边缘有季节不完整的数据时用月级精度。
- 多段适用于分离样本标定（用一段标定，用同一工程的另一段验证）。
- period 会裁剪到工程的输出窗口内（遵循 NYSKIP）。

### period 与 `rowRanges`

模板根据 `id`、`period` 和从 IPRINT 推导的时间步长计算 `rowRanges`。

```yaml
# 月尺度输出，62 个子流域
rowRanges:
  - [71, 753, 62]    # 每年 1-12 月，跳过 MON=13
```

在模板模式下你很少需要手写这些——SWAT 模板帮你算好了。

## 4. 参数写入策略

HydroPilot 的参数系统有两层：**design**（优化器看到的东西）和 **physical**（写入文件的东西）。根据参数与模型空间结构的关系选择你的策略。

### 策略 A：全局参数（无 filter）

每个 HRU 或河段获得相同的值。最简单的情况。

```yaml
parameters:
  design:
    - name: CN2
      bounds: [35, 98]
    - name: ALPHA_BF
      bounds: [0, 1]
    - name: GW_DELAY
      bounds: [0, 500]

  physical:
    - name: CN2
      mode: v
    - name: ALPHA_BF
      mode: v
    - name: GW_DELAY
      mode: v
```

`mode: v` 表示直接写入值（不做相对变化，不做绝对偏移）。这是默认也是最常用的模式。

**适用场景：** 整个流域使用统一参数。一个 design 变量 = 每个匹配文件中的一个 physical 参数。

### 策略 B：HRU 过滤参数

不同 HRU 组获得独立标定的值。

```yaml
parameters:
  design:
    - name: CN2_AGRL
      bounds: [35, 98]
    - name: CN2_FRST
      bounds: [30, 90]
    - name: ALPHA_BF
      bounds: [0, 1]

  physical:
    - name: CN2_AGRL
      mode: v
      filter:
        land_use: AGRL
    - name: CN2_FRST
      mode: v
      filter:
        land_use: FRST
    - name: ALPHA_BF
      mode: v
```

每个带 filter 的 physical 参数只写入匹配的 HRU。`ALPHA_BF`（无 filter）写入所有 HRU。

**适用场景：** 当不同土地利用、土壤类型或坡度等级需要独立标定。每个条件获得自己的 design 变量和优化器自由度。

### 策略 C：Transformer（多对多映射）

当优化器调优的变量少于 physical 参数数量，或 design 值写入前需要变换时使用。

```yaml
parameters:
  design:
    - name: CN2_factor      # 优化器调一个因子
      bounds: [-0.2, 0.2]
    - name: ESCO_val
      bounds: [0.1, 0.9]
    - name: GW_DELAY_val
      bounds: [0, 500]
    - name: SURLAG_val
      bounds: [0.5, 24]

  physical:
    - name: CN2_AGRL
      mode: v
      filter:
        land_use: AGRL
    - name: CN2_URHD
      mode: v
      filter:
        land_use: URHD
    - name: ESCO_1_30
      mode: v
    - name: ESCO_31_62
      mode: v
    - name: GW_DELAY
      mode: v
    - name: SURLAG
      mode: v

  transformer: monthly_transform
```

transformer 函数（在 `functions` 中声明为 `kind: external`）接收 design 向量 `X`，返回 physical 向量 `P`：

```yaml
functions:
  - name: monthly_transform
    kind: external
    file: monthly_transform.py
```

在这个例子中，4 个 design 参数通过 transformer 映射到 6 个 physical 参数。优化器只看到 4 维。

**适用场景：**
- 空间正则化（一个因子 → 多个带标定偏移的 HRU 组）。
- 优化器空间和 physical 空间之间的非线性变换。
- design 变量少于 physical 目标。

### 策略 D：离散参数

```yaml
design:
  - name: landuse_code
    type: discrete
    bounds: [1, 3]
    sets: [1, 2, 3]
```

离散变量在 UQPyL 中映射为 `varType=2`，以 `sets` 为候选值。

**适用场景：** 分类选择（土地利用情景、管理方案）。值必须是数值。

### 策略总览

| 策略 | Design → Physical | Filter | 适用 |
|---|---|---|---|
| 全局 | 1:1 | 无 | 统一参数 |
| HRU 过滤 | 每组 1:1 | 每个 physical 上加 `filter` | 空间差异 |
| Transformer | M:N 通过函数 | 可选 | 正则化、非线性变换 |
| 离散 | 分类集合 | 可选 | 土地利用/管理情景 |

## 5. HRU 过滤

filter 决定一个 physical 参数写入哪些 HRU 文件。没有 filter 的参数条目写入所有 HRU。

### 过滤字段

```yaml
filter:
  subbasin: [1, 3, 5]       # 子流域 ID
  land_use: AGRL             # .hru 表头中的土地利用代码
  soil: "Haplic Luvisols"    # .hru 表头中的土壤名称
  slope: "30-45"             # .hru 表头中的坡度等级
  not:
    slope: "0-5"             # 排除的坡度等级
```

| 字段 | 类型 | 匹配内容 |
|---|---|---|
| `subbasin` | int 或列表 | 子流域 ID |
| `land_use` | string 或列表 | `.hru` 表头中的 Luse 字段 |
| `soil` | string 或列表 | `.hru` 表头中的 Soil 字段 |
| `slope` | string 或列表 | `.hru` 表头中的 Slope 字段 |
| `not` | 子过滤 | 排除块 |

### AND/OR 逻辑

- **同一字段，多个值 → OR。** `subbasin: [1, 3, 5]` 匹配子流域 1、3 或 5。
- **不同字段 → AND。** `land_use: AGRL` 且 `soil: "Haplic Luvisols"` 只匹配同时满足两个条件的 HRU。
- **`not` 块 → 排除。** `not: {slope: "0-5"}` 从匹配集合中移除平坡 HRU。

```yaml
# 匹配满足以下条件的 HRU：
#   - 在子流域 1 到 30 中
#   - AND 土地利用为 AGRL 或 FRST
#   - AND 不在 "0-5" 坡度等级中
filter:
  subbasin: [1, 30]          # 注意：不支持范围语法，需显式列出
  land_use: [AGRL, FRST]     # AGRL 或 FRST
  not:
    slope: "0-5"             # 排除平坡
```

注意：`subbasin` 不支持范围语法。子流域 ID 需显式列出：`[1, 2, 3, ..., 30]`。

### 文件展开

带有 `*.mgt` 或 `*.hru` 文件模式的 HRU 过滤参数在模板展开时展开为具体文件名。每个匹配的 HRU 文件独立写入：

```text
Filter 匹配 HRU 1（子流域 1，AGRL）→ 写入 000010001.mgt
Filter 匹配 HRU 3（子流域 1，FRST）→ 写入 000010003.mgt
```

全局文件如 `basins.bsn` 不展开——模式保持原样。

## 6. 示例模式

### 最简单的全局参数案例

三个参数，一个序列，一个目标。无 filter，无 transformer。这是首次 SWAT 2012 日尺度运行的典型配置：

```yaml
version: swat

basic:
  projectPath: ./TxtInOut
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
  physical:
    - name: CN2
      mode: v
    - name: ALPHA_BF
      mode: v
    - name: GW_DELAY
      mode: v

series:
  - id: flow
    sim:
      file: output.rch
      id: 33
      period: [2010, 2015]
      variable: FLOW_OUT
    obs:
      file: obs_flow.txt
      rowRanges:
        - [1, 2190]
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
    ref: nse_flow
    sense: max
```

参考：`examples/test_daily.yaml`。

### HRU 过滤案例

按土地利用拆分 CN2 标定，保持 ALPHA_BF 和 GW_DELAY 全局：

```yaml
parameters:
  design:
    - name: CN2_AGRL
      bounds: [35, 98]
    - name: CN2_FRST
      bounds: [30, 90]
    - name: CN2_URHD
      bounds: [40, 95]
    - name: ALPHA_BF
      bounds: [0, 1]
    - name: GW_DELAY
      bounds: [0, 500]

  physical:
    - name: CN2_AGRL
      mode: v
      filter:
        land_use: AGRL
    - name: CN2_FRST
      mode: v
      filter:
        land_use: FRST
    - name: CN2_URHD
      mode: v
      filter:
        land_use: URHD
    - name: ALPHA_BF
      mode: v
    - name: GW_DELAY
      mode: v
      filter:
        subbasin: [1, 2, 3, 4, 5]
    - name: GW_DELAY
      mode: v
      filter:
        subbasin: [6, 7, 8, 9, 10]
```

每个 CN2 变体是一个独立的 design 变量。GW_DELAY 拆分为两个区域（子流域 1–5 和 6–10），各自独立标定。

参考：`examples/test_monthly_complex.yaml`（展示了此模式并叠加 transformer）。

### 多序列案例

同时标定同一子流域的径流和总氮：

```yaml
series:
  - id: flow
    sim:
      file: output.rch
      id: 62
      period: [2019, 2021]
      colSpan: [50, 61]
    obs:
      file: obs_flow_monthly.txt
      rowRanges:
        - [1, 36]
      colSpan: [1, 12]

  - id: tn
    sim:
      file: output.rch
      id: 62
      period: [2019, 2021]
      colSpan: [76, 87]
    obs:
      file: obs_tn_monthly.txt
      rowRanges:
        - [1, 36]
      colNum: 1

functions:
  - name: NSE
    kind: builtin

derived:
  - id: nse_flow
    call:
      func: NSE
      args: [flow.sim, flow.obs]
  - id: nse_tn
    call:
      func: NSE
      args: [tn.sim, tn.obs]

objectives:
  - id: obj_nse_flow
    ref: nse_flow
    sense: max
  - id: obj_nse_tn
    ref: nse_tn
    sense: max
```

两个序列都从同一个 `output.rch` 文件读取，但列范围不同。每个序列有自己的 derived 值和 objective。多目标优化由 UQPyL 算法处理（如 `UQPyL.optimization.moea` 中的 NSGA-II）。

参考：`examples/test_monthly_series.yaml`。

## 7. 决策流程总览

```text
起点：SWAT 2012 工程目录（TxtInOut）

1. 用哪个输出文件？
   ├── 出口断面流量  → output.rch
   ├── 子流域汇总    → output.sub
   └── HRU 级变量    → output.hru

2. 用哪个变量或列？
   ├── 变量在数据库中  → 用 variable: FLOW_OUT
   └── 自定义/未知     → 用 colSpan: [50, 61]

3. 什么时段？（时间步长由工程 IPRINT 自动推导）
   ├── 完整标定窗口     → period: [2010, 2015]
   └── 部分/子集        → period: ["2019-06", "2021-09"]

4. 参数策略？
   ├── 所有 HRU 相同    → 无 filter（全局）
   ├── 按土地利用/土壤  → filter: {land_use: AGRL}
   ├── 正则化           → transformer
   └── 离散情景         → type: discrete

5. 目标？
   ├── 单一指标         → 一个 derived，一个 objective
   └── 多个指标         → 多个 derived + objectives
```

## 另见

- [SWAT 2012 日尺度分步指南](swat-daily-step-by-step.md) — 从零到首次可运行的日尺度案例。
- [SWAT 2012 月尺度指南](swat-monthly-guide.md) — 将日尺度工作流适配到月尺度输出。
- [SWAT 2012 模板参考](../templates/swat-2012.md) — 简洁的模板配置参考。
- [配置参考](../configuration-reference.md) — 所有 general 模式字段。
- [示例](../examples.md) — 完整示例说明和前置条件。
