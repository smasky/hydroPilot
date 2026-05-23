# 示例

本文梳理了 HydroPilot 附带的示例配置和辅助脚本，帮助你找到适合自己项目的起点。

## 快速定位：我应该从哪个示例开始？

| 如果你... | 从这开始 |
|---------------|-----------|
| 刚接触 HydroPilot | `test_daily.yaml` —— 最简单的 SWAT 2012 示例 |
| 使用非 SWAT 模型或想要完全掌控工作流 | `test_daily_general.yaml` 或 `test_xaj_general.yaml` |
| 处理月尺度数据 | `test_monthly.yaml` |
| 需要带空间过滤的参数率定 | `test_monthly_complex.yaml` |
| 使用 XAJ（基于 CSV 的模型） | `test_xaj.yaml` |
| 想了解更高级的功能 | 浏览下面的 complex、series 和 warning 示例 |

所有示例用于文档说明和冒烟测试。在真正用于率定之前，请根据你自己的项目修改路径、参数和序列。

---

## 示例配置一览

| 文件 | 版本 | 模型 | 时间步长 | 亮点 |
|------|---------|-------|----------|------------|
| `test_daily.yaml` | `swat` | SWAT 2012 | 日尺度 | 3 个参数，单目标（NSE） |
| `test_daily_general.yaml` | `general` | — | 日尺度 | 同一场景的完整展开版配置 |
| `test_monthly.yaml` | `swat` | SWAT 2012 | 月尺度 | 子流域过滤、时间段选择 |
| `test_monthly_general.yaml` | `general` | — | 月尺度 | 同一场景的完整展开版配置 |
| `test_monthly_complex.yaml` | `swat` | SWAT 2012 | 月尺度 | 参数变换、HRU 过滤、多目标、诊断项、外部函数 |
| `test_monthly_series.yaml` | `swat` | SWAT 2012 | 月尺度 | 时间段切片（年、月、日）、派生序列、多序列 |
| `test_monthly_series_warning.yaml` | `swat` | SWAT 2012 | 月尺度 | 调用型序列、warning/诊断行为演示 |
| `test_xaj.yaml` | `xaj` | XAJ | — | RIVID 过滤、CSV reader/writer |
| `test_xaj_general.yaml` | `general` | — | — | 同一 XAJ 场景的完整展开版配置 |

---

## General 示例（`version: general`）

通用模式配置直接使用完整的 HydroPilot schema。不会经过模型模板展开——你需要显式指定每一个 reader、writer 和文件位置。

### `test_daily_general.yaml`

一份日尺度 SWAT 2012 率定配置，以通用格式书写。三个参数（CN2、ALPHA_BF、GW_DELAY）通过定宽格式 writer 写入 `.mgt` 和 `.gw` 文件。观测值以 `colNum` 方式从文本文件中读取。

适合用来理解模板模式配置展开后的完整 schema 长什么样。

### `test_monthly_general.yaml`

与日尺度版本相同的三参数场景，但时间步长为月尺度。展示了多段 `rowRanges` —— 输出文件以三段不连续的范围读取（每年取第 1–11 个月，跳过年度均值行）。

### `test_xaj_general.yaml`

一份 XAJ 模型的通用格式配置。显式定义了 CSV reader 和 writer。两个参数（KC、WM）写入 `parameters.csv`。两条序列：分别从不同的 CSV 输出文件中读取流量和径流深。

---

## SWAT 2012 示例（`version: swat`）

SWAT 2012 配置使用变量名（`FLOW_OUT`、`TN_OUT`）代替原始列范围，参数名（`CN2`、`ALPHA_BF`）也无需手写文件布局。这些信息由模板通过 SWAT 2012 知识库自动解析。

#### `test_daily.yaml`

最简单的 SWAT 2012 示例。三个参数全局率定（无 HRU 过滤）。一条序列（`flow`），从 33 号子流域的 `output.rch` 中读取 `FLOW_OUT`，时段为 2010–2015 年，日尺度。观测数据来自文本文件。单目标（NSE，最大化）。

修改路径后可执行：

```bash
hydropilot-validate examples/test_daily.yaml
hydropilot-test examples/test_daily.yaml
```

#### `test_monthly.yaml`

月尺度版本，62 号子流域，时段 2019–2021 年。模拟列使用 `colSpan` 而非变量名查找。观测值同样用 `colSpan`（观测文件第 1–12 列）。

与日尺度示例的主要区别：
- 时间步长由工程 `file.cio` 中的 IPRINT 设置决定（0=月尺度，1=日尺度），不在配置中指定。SWAT 模板模式下校验器会拒绝 `sim.timestep`。
- SWAT 输出行按月计算，跳过年度均值行（MON=13）。
- `rowRanges` 使用三段 `[start, end, step]` 格式，step 等于子流域数。

#### `test_monthly_complex.yaml`

功能最丰富的示例。展示了：

- **参数变换器**：4 个设计参数通过 `monthly_transform.py` 映射为 6 个物理参数。设计空间的值（CN2_factor、ESCO_val 等）在写入前先经过变换。
- **HRU 过滤**：CN2 参数按土地利用（`AGRL` 和 `URHD`）过滤。ESCO_HRU 按两个子流域范围分段（1–30 和 31–62）。过滤引擎（`filterHrus`）将 `*.mgt` 模式解析为每个 HRU 的具体文件名。
- **多序列**：从同一个 `output.rch` 文件中读取两条序列（`flow` 和 `tn`），使用不同的列范围。
- **多目标**：两个 NSE 目标（流量和 TN），均为最大化。
- **诊断项**：KGE、RMSE，以及一个从 TN 序列计算的外部函数（`calc_annual_tn_load`）——诊断项被计算但不参与优化。
- **外部函数**：`monthly_transform.py` 提供参数变换器；`calc_tn_load.py` 提供年 TN 负荷诊断。

#### `test_monthly_series.yaml`

展示时间段切片和派生序列：

- 两个 sim 块从同一个子流域（62）读取同一个变量（`FLOW_OUT`），但使用不同的时段格式：`[2019-02, 2021-11]`（月精度）和 `[2019-02-03, 2021-11-01]`（日精度，对于月尺度输出会被截断到月边界）。
- 通过外部函数生成派生序列：`flow_times_two` 对模拟序列做变换，`series_equal` 比较两个不同时段切片的序列是否相等。
- 两个派生结果都以诊断项形式呈现。

#### `test_monthly_series_warning.yaml`

展示调用型 sim 块和警告行为：

- 第二条序列（`flow_matrix`）使用 `sim.call` 而非 `sim.file`——序列值通过调用 `flow_as_matrix` 计算，以第一条序列为输入，输出 2D（矩阵形态）结果。
- 调用函数返回的非标量序列（矩阵）会触发运行时 warning，因为下游目标和诊断项通常期望标量或一维序列。
- reporter 的 `flushInterval` 设为 1，以便及时显示 warning。

## XAJ 示例（`version: xaj`）

XAJ（新安江）模型是基于 CSV 的水文模型。其模板使用 CSV reader 和 writer 而非定宽文本。

#### `test_xaj.yaml`

一份双参数（KC、WM）的 XAJ 配置：

- **按 RIVID 过滤参数**：KC 过滤到特定河段（`rivid: 60711600`）。WM 应用于所有河段（无过滤）。XAJ 模板从工程的 `parameters.csv` 中按 RIVID 解析参数行。
- **使用变量名的序列**：`Streamflow` 和 `Runoff` 通过 XAJ 序列数据库解析。带有 `idHeader: true` 的变量（如 `Runoff`）需要指定 `rivid` 来定位正确的输出列。
- **CSV 输入输出**：reader 和 writer 都使用 CSV 格式，支持可配置的分隔符、`headSkip` 和 `colNum`。

---

## 日尺度与月尺度示例对比

日尺度和月尺度示例在用户层面有三个关键区别：

| 方面 | 日尺度 | 月尺度 |
|--------|-------|---------|
| 时间步长来源 | 工程 `file.cio` IPRINT=1，由模板自动识别 | 工程 `file.cio` IPRINT=0，由模板自动识别 |
| `period` 精度 | 通常只到年：`[2010, 2015]` | 通常只到年：`[2019, 2021]` |
| 输出行数 | 每个子流域每年 365/366 行 | 每个子流域每年 12 行（+ 1 行年度均值，跳过） |
| `rowRanges` 结构 | 连续范围，step = 子流域数 | 多段范围，跳过年度均值行 |
| 观测文件 | `obs_flow.txt`（日值） | `obs_flow_monthly.txt`（月值） |

模板模式示例（`version: swat`）会自动处理输出行计算和时间步长识别——时间步长从工程 `file.cio` 的 IPRINT 读取，你只需提供 `id` 和 `period`。通用模式示例则会显式展示解析后的 `rowRanges`。

---

## 辅助脚本

`examples/` 目录下有四个 Python 脚本，提供可复用的外部函数。

### `monthly_transform.py`

一个**参数变换器**，将 4 个设计参数映射为 6 个物理参数：

```
X[0] (CN2_factor)    → P[0] (AGRL 的 CN2)、P[1] (URHD 的 CN2)
X[1] (ESCO_val)      → P[2] (子流域 1–30 的 ESCO)、P[3] (子流域 31–62 的 ESCO)
X[2] (GW_DELAY_val)  → P[4] (全局 GW_DELAY)
X[3] (SURLAG_val)    → P[5] (全局 SURLAG)
```

由 `test_monthly_complex.yaml` 作为 `transformer` 使用。在 functions 块中以 `kind: external` 引用，`file: "monthly_transform.py"`。

### `series_transform.py`

两个序列操作函数：

- `flow_times_two(flow_month_sim)` —— 将序列乘以 2，作为派生序列变换使用。
- `series_equal(flow_month_sim, flow_date_sim)` —— 比较两个序列是否相等（允许 NaN 容忍），相等返回 1.0，不等返回 0.0。用于验证同一子流域在不同时段切片下是否产生相同结果。

由 `test_monthly_series.yaml` 使用。

### `series_transform_warning.py`

两个函数，其中一个设计为触发诊断 warning：

- `flow_times_two(flow_month_sim)` —— 与 `series_transform.py` 中相同的标量变换。
- `flow_as_matrix(flow_month_sim)` —— 将序列与自身堆叠，返回 2D 数组。这会产生非标量派生序列，触发运行时 warning，因为矩阵形态的输出不在下游目标/诊断项的预期之内。

由 `test_monthly_series_warning.yaml` 使用。

### `calc_tn_load.py`

一个**外部评估函数**，从月尺度 TN 序列计算年均 TN 负荷：

```python
def calc_annual_tn_load(tn_sim):
    # 累加月值，除以年数
```

由 `test_monthly_complex.yaml` 通过 `derived` 作为诊断项使用。函数接收一个参数（`tn.sim`），返回标量。

---

## 校验示例配置

使用 `hydropilot-validate` 在不运行模型的情况下检查配置：

```bash
# 模板模式 SWAT 2012 配置
hydropilot-validate examples/test_daily.yaml

# 通用模式配置
hydropilot-validate examples/test_daily_general.yaml
```

校验器会报告错误（缺少文件、语法无效）和警告（观测/模拟数据量不匹配）。它不执行模型。

注意：部分示例引用的工程目录（`E:\DJBasin\TxtInOutFSB`、`E:\BMPs\TxtInOut`）仅存在于作者本机。校验时会出现 `projectPath: directory not found`。请先将 `basic.projectPath` 改到本地 SWAT 2012 工程路径再运行校验。

## 冒烟测试示例

使用 `hydropilot-test` 执行一次完整的冒烟测试（用默认参数向量做一次评估）：

```bash
hydropilot-test examples/test_daily.yaml
```

这会加载配置、创建临时工程副本、写入默认参数、运行模型命令、提取结果并写出一份测试报告。测试期间强制 `parallel: 1` 且 `keepInstances: true`。

## 单次评估

使用 `hydropilot-run` 配合 run YAML 评估一组特定参数：

```yaml
# run_daily.yaml
config: examples/test_daily.yaml
mode: design
values:
  CN2: 72.5
  ALPHA_BF: 0.3
  GW_DELAY: 120
```

```bash
hydropilot-run run_daily.yaml
```

`hydropilot-run` 是单次评估入口——评估一组参数向量并打印结果。批量评估或优化请用 Python API（`SimModel`）。

---

## 将示例适配到实际项目

示例配置是文档和测试产物，不是开箱即用的率定配置。适配时需要：

1. **修改 `basic.projectPath`** 为你本地的 SWAT 2012 TxtInOut 目录或 XAJ 工程目录。
2. **修改 `basic.command`** 匹配你本地的模型可执行文件名和路径。
3. **检查参数范围**——示例中的范围是示意性的，不一定适合你的流域。
4. **核对输出文件结构**——子流域数量、输出变量列、HRU 土地利用/土壤/坡度分类因项目而异。
5. **替换观测文件**——将 `obs.file` 指向你自己的实测数据。
6. **调整时间步长和时段**以匹配你的率定期。
7. **确认 `version`**——SWAT 2012 工程用 `version: swat`（模板自动展开），如需完全掌控每个 reader/writer/文件位置则用 `version: general`。
