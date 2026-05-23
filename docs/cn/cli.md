# CLI 参考

HydroPilot 提供四个命令行入口，分别用于配置校验、冒烟测试、参数应用和单次评估。

## 安装

安装包后四个命令即可用：

```bash
pip install hydropilot
```

它们在 `pyproject.toml` 中注册为 console scripts，使用时不需要先进入 Python。

---

## `hydropilot-validate`

校验配置文件。

```bash
hydropilot-validate <config.yaml>
```

### 做了什么

1. 解析 YAML 配置文件。
2. 如果配置使用了模型专属版本（如 `version: "swat"` 或 `version: "xaj"`），会先经过对应模板展开为通用格式配置。
3. 执行通用格式配置的结构校验。
4. 把诊断信息逐行打印到 stdout。

### 退出码

| 码 | 含义 |
|------|---------|
| 0 | 校验通过（存在 warning 时也会返回 0） |
| 1 | 校验未通过（至少一条 error 级诊断） |

### 输出示例

```
ERROR basic.projectPath: directory not found: /nonexistent/project
```

```
WARNING series[flow].obs: observation file has fewer rows than sim
Validation passed: config.yaml
```

### 使用说明

- 配置文件必须存在且是合法的 YAML。
- SWAT 2012 或 XAJ 配置会先展开再校验，所以模板层面的错误（如缺少 `file.cio`）会以校验诊断的形式呈现。
- 这个命令是只读的：不会运行模型，也不会修改任何文件。

---

## `hydropilot-test`

执行一次完整的配置冒烟测试。

```bash
hydropilot-test <config.yaml>
```

### 做了什么

1. 加载并校验配置（与 `hydropilot-validate` 共享同一条路径）。
2. 从设计参数范围中构建一个默认的测试向量。
3. 创建一个临时的工程副本，写入参数，运行一次模型命令，然后提取结果。
4. 计算所有的目标函数、约束项和诊断项。
5. 在终端打印摘要，并把 `test-report.md` 和 CSV 产物写入归档目录。

### 退出码

| 码 | 含义 |
|------|---------|
| 0 | 冒烟测试通过 |
| 1 | 冒烟测试失败 |

### 使用说明

- 会强制设置 `parallel = 1` 和 `keepInstances = true`，不受配置文件中对应字段的影响。
- 一次完整的模型执行会发生——这不是空跑。
- 用这个命令来验证一份配置是否完全打通：工程文件是否存在、模型可执行文件是否能跑起来、输出文件是否可读、评估是否能产出结果。

---

## `hydropilot-apply`

将设计参数或物理参数写入一个工程副本。

```bash
hydropilot-apply <apply.yaml>
```

### Apply YAML 格式

apply YAML 引用一份 HydroPilot 配置并指定要写入的参数：

```yaml
config: path/to/config.yaml
mode: design        # 或 "physical"
values:
  CN2: 72.5
  ALPHA_BF: 0.3
  GW_DELAY: 120
outDir: ./applied_project
```

- `config` —— 指向 HydroPilot 配置 YAML 的路径。
- `mode` —— `"design"`（把设计空间的值转换为物理参数再写入）或 `"physical"`（直接把物理参数值写入模型输入文件）。
- `values` —— 以参数名为 key 的字典。命名 key 会与配置中的参数列表做核对；存在多余或缺失的 key 会报错。
- `outDir` —— 目标目录。不能是已有目录。工程会先被复制到该目录，再写入参数。

### 退出码

| 码 | 含义 |
|------|---------|
| 0 | 参数写入成功 |
| 1 | 出错（YAML 格式错误、参数缺失、目标目录已存在等） |

### 使用说明

- `mode: design` 会走完整的设计到物理参数链路：设计值先经过参数转换后，通过注册的 writer 写入模型输入文件（SWAT 2012 用定宽格式写入，XAJ 用 CSV 格式写入）。
- `mode: physical` 直接写入物理参数值，跳过设计层转换。
- 输出目录是一个完整、可直接运行的工程副本。

---

## `hydropilot-run`

从 run YAML 执行一次单次评估。

```bash
hydropilot-run <run.yaml>
```

### Run YAML 格式

```yaml
config: path/to/config.yaml
mode: design           # 或 "physical"
values:
  - 72.5               # 按位置匹配，需与设计参数顺序一致
  - 0.3
  - 120
```

也可以使用命名值：

```yaml
config: path/to/config.yaml
mode: design
values:
  CN2: 72.5
  ALPHA_BF: 0.3
  GW_DELAY: 120
```

### 做了什么

1. 加载 `config` 引用的配置。
2. 用给定的参数值执行一次模型评估。
3. 打印结果摘要，包含目标函数值、约束值、诊断值和输出文件路径。

### 退出码

| 码 | 含义 |
|------|---------|
| 0 | 运行通过 |
| 1 | 运行失败 |

### 适用范围

`hydropilot-run` 是一个**单次评估入口**——评估一组参数向量并打印结果。它不做优化、不做批量执行、也不做实验管理。需要多组评估或优化时，请用 Python API（`SimModel`）或通过 `UQPyLAdapter` 接入 UQPyL。

---

## 命令对比

| 命令 | 作用 | 是否运行模型 | 是否写入文件 |
|---------|---------|-------------|---------------|
| `hydropilot-validate` | 检查配置是否正确 | 否 | 否 |
| `hydropilot-test` | 完整冒烟测试 | 是，一次 | 是（报告 + CSV） |
| `hydropilot-apply` | 将参数写入工程副本 | 否 | 是（工程副本） |
| `hydropilot-run` | 从 run YAML 做单次评估 | 是，一次 | 是（归档目录） |
