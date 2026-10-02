# Python API 参考

hydroPilot 的公开 Python API 提供模型模拟、批量运行以及可选的 UQPyL 集成的编程入口。

## 主要导入

```python
from hydropilot import SimModel, BatchRunResult
from hydropilot.integrations import UQPyLAdapter
```

以上是唯一稳定的公开导入。其他模块和类属于内部实现，可能在没有预告的情况下变更。

---

## `SimModel`

`SimModel` 是从 Python 运行模拟的主要入口。

```python
from hydropilot import SimModel

model = SimModel("path/to/config.yaml")
```

### 构造方法

`SimModel(cfgPath: str)` 加载并校验 `cfgPath` 处的配置。配置中的 `version` 决定是否使用模型模板（SWAT 2012 或 XAJ）进行展开。成功加载后，运行时会话即被初始化。

### 上下文管理器

`SimModel` 支持上下文管理器协议。退出时会自动关闭会话：

```python
with SimModel("path/to/config.yaml") as model:
    result = model.run([72.5, 0.3, 120])
# 会话在此处关闭
```

### `run(X)`

使用给定的设计参数值运行一次或多次评估。

```python
# 单次评估 — 一维数组
result: BatchRunResult = model.run([72.5, 0.3, 120])

# 批量评估 — 二维数组，形状为 (样本数, 输入数)
result: BatchRunResult = model.run([
    [72.5, 0.3, 120],
    [65.0, 0.5, 200],
    [80.0, 0.2, 80],
])
```

- `X` — 设计参数值的列表或 numpy 数组，顺序与配置中 `parameters.design` 列表的定义顺序一致。一维数组执行单次评估；形状为 `(样本数, 输入数)` 的二维数组执行批量运行。
- 返回 `BatchRunResult`。批量运行时，`result.objs` 的形状为 `(样本数, 目标数)`。

`run(X)` 组合参数写入、模拟和后处理，独立于 UQPyL。会话初始化时准备 `basic.workPath` 下的项目副本，后续模拟复用这些副本。

每个样本的内部流程：

1. 批量调度入口 `_runSimulation(X)` 为每个样本取得工作副本，调用 `_apply(workPath, X, context)` 完成设计值到物理参数的变换、输入写入和写入信息记录。
2. `_simulate(workPath, context)` 在同一份已准备好的副本中执行 `basic.command` 并提取序列。调度层在提取后释放副本，组装独立的批量 context，并提交模拟快照归档；此时指标为 pending。
3. `_post` 从 context 计算 derived、目标、约束和诊断，缓存结果，并提交快照更新同一条样本记录。
4. reporter 将快照提交到 SQLite，再从已提交数据导出 CSV 和错误日志。

关闭会话时会等待 reporter 完成归档，并清理项目副本；`keepCopies: true` 时恢复涉及的输入文件到会话开始时的内容，保留副本、输出与日志。调试时可另设 `reset: true`，每次模拟后也恢复输入；默认 `false`。

内部 `_apply` 与 `_simulate` 可以分别组合：`_apply` 不运行模型、不分配评估记录；`_simulate` 使用已写好的输入，不重复变换或写入参数。批量调度负责编号、副本持有、错误处理和归档。需要单独生成项目副本时，使用下面的公开 `apply_design` 或 `apply_params`。

### `apply_design(X, out_dir)`

将设计参数应用到一份全新的项目副本。

```python
model.apply_design([72.5, 0.3, 120], "./my_project")
```

- 通过完整的设计到物理参数流水线对设计值进行变换。
- 将物理参数写入输出目录中的模型输入文件。
- 输出目录可用于人工检查或手动运行。

### `apply_params(P, out_dir)`

直接将物理参数应用到全新的项目副本，绕过设计层。

```python
model.apply_params([0.75, 0.003, 0.22], "./my_project")
```

- `P` — 物理参数值的列表或数组，顺序与配置中 `parameters.physical` 一致。
- 适用于应用已解析好的物理参数。

### 属性

| 属性 | 类型 | 说明 |
|----------|------|-------------|
| `nInput` | `int` | 设计输入参数的数量 |
| `xLabels` | `list[str]` | 设计参数标签列表；指定 scope 时包含 scope，例如 `ESCO.bsn` |
| `lb` | `list[float]` | 各设计参数的下界 |
| `ub` | `list[float]` | 各设计参数的上界 |
| `varType` | `list[int]` | 变量类型编码（0=float, 1=int, 2=discrete） |
| `varSet` | `list` | 各设计参数的离散值集合（离散类型时为有效值列表，其他类型为空列表） |
| `nOutput` | `int` | 目标数量 |
| `nConstraints` | `int` | 约束数量 |
| `optType` | `list[str]` | 各目标的优化方向字符串（`"min"` 或 `"max"`） |
| `cfgPath` | `str` | 已加载配置文件的路径 |

---

## `BatchRunResult`

`SimModel.run()` 及内部批量执行器返回的数据类。

```python
from hydropilot import BatchRunResult
```

### 字段

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `X` | `np.ndarray` | 已评估的设计参数值，形状 `(样本数, 输入数)` |
| `P` | `np.ndarray` 或 `None` | 解析后的物理参数值，形状 `(样本数, 物理参数数)` |
| `objs` | `np.ndarray` | 目标函数值，形状 `(样本数, 目标数)` |
| `cons` | `np.ndarray` 或 `None` | 约束值，形状 `(样本数, 约束数)`。未定义约束时为 `None`。 |
| `diags` | `np.ndarray` 或 `None` | 诊断值，形状 `(样本数, 诊断数)`。未定义诊断时为 `None`。 |
| `series` | `dict[str, np.ndarray]` 或 `None` | 按序列 id 索引的提取时间序列，每个形状 `(样本数, 时间步数)`。未执行序列提取时为 `None`。 |
| `obs` | `dict[str, np.ndarray]` 或 `None` | 按序列 id 索引的观测数组，每个形状 `(时间步数,)`。未配置观测时为 `None`。 |

### 使用示例

```python
result = model.run([72.5, 0.3, 120])
print(result.objs)     # 例如 [[0.78]]
print(result.X)        # [[72.5, 0.3, 120.0]]
```

单次运行时，数组维度中 `样本数 = 1`。

---

## `UQPyLAdapter`

将 `SimModel` 包装为 UQPyL `ModelProblem`，用于 UQPyL 的优化和校准算法。

```python
from hydropilot.integrations import UQPyLAdapter

adapter = UQPyLAdapter("path/to/config.yaml")
```

### 说明

`UQPyLAdapter` 直接继承 `UQPyL.problem.ModelProblem` 的公开接口，内部委托给 `SimModel` 执行模型。它从 HydroPilot 配置中提取问题定义（`nInput`、`nObj`、`nCon`、边界、变量类型、目标方向和标签），并构建 `obs`、`mask`、`seriesLabels`。

### 上下文管理器

```python
with UQPyLAdapter("config.yaml") as adapter:
    result = adapter.evaluate(X)
    objs = result.objs
```

### 方法

#### `evaluate(X, target=None)`

```python
result = adapter.evaluate(X)
objs = result.objs
cons = result.cons
sim = result.sims
```

运行模型并返回 `UQPyL.problem.Eval` 对象。`result.sims` 的形状为 `(n_samples, n_time, n_series)`。

`target` 可选 `None`（全部字段）、`"objs"`、`"cons"` 或 `"sims"`。默认执行模拟与全部后处理，包括写入归档的诊断。`"objs"`、`"cons"` 只计算对应块及其依赖；`"sims"` 跳过后处理。每次调用都会启动新的模拟。

#### 分开调用模拟与评估

| 方法 | 返回内容 |
|---|---|
| `simulate(X)` | `SimContext` 子类，包含 `sims`、`obs`、`mask`，以及 `simulation` 中完整的 HydroPilot 模拟数据；此时不计算指标 |
| `simFunc(X)` | 形状为 `(n_samples, n_time, n_series)` 的模拟数组 |
| `objFunc(X, context)` | 计算该 context 的目标及其依赖，已计算时复用结果 |
| `conFunc(X, context)` | 计算该 context 的约束及其依赖；未配置约束时返回 `None` |

```python
with UQPyLAdapter("config.yaml") as problem:
    contextA = problem.simulate(XA)
    contextB = problem.simulate(XB)
    objA = problem.objFunc(XA, contextA)
    physicalA = contextA.simulation.P
```

每个 context 保存自己的模拟数据与后处理状态。目标／约束调用按需计算，不再次运行模型；重复调用复用结果。各阶段更新同一条样本归档记录，只模拟时也保存记录，未计算指标标记为 pending。context 必须由同一适配器返回，`X` 必须与产生它的参数相符；参数不匹配、另一适配器的 context、手工构造的 context 都会触发 `ValueError`。`flattenSim`、`flattenObs`、`flattenMask` 也直接继承原生实现。

有观测数据时，暴露带 `obs` 的序列；没有观测数据时，暴露全部配置的模拟序列，`obs` 和 `mask` 为 `None`，可用于普通优化。`seriesLabels` 为这些序列的 id，至少需要一条模拟序列。观测缺失和观测长度补齐位置在 `mask` 中为 `True`，模拟 NaN 不会改变这个 mask。

### 适用范围

适配器提供 UQPyL `ModelProblem` 接口：问题定义、基于模拟序列的评估接口，以及观测序列元数据。它不实现 UQPyL 专属的分析方法。

### 示例：使用适配器

```python
from hydropilot.integrations import UQPyLAdapter

with UQPyLAdapter("config.yaml") as adapter:
    # 评估一个参数向量
    result = adapter.evaluate(X)
    objs = result.objs
    cons = result.cons

    sim = result.sims
```

适配器可传递给任何接受 `ModelProblem` 实例的 UQPyL 算法。

当前的 UQPyL 优化器使用 `algorithm.run(problem)`：

```python
from UQPyL.optimization.soea import GA
from hydropilot.integrations import UQPyLAdapter

with UQPyLAdapter("config.yaml") as problem:
    algorithm = GA(nPop=20, maxFEs=100, verboseFlag=False, logFlag=False, saveFlag=False)
    result = algorithm.run(problem, seed=123)
    print(result.bestDecs)
    print(result.bestObjs)
```

同一个适配器也可直接用于 GLUE、SUFI2 等校准方法；这些比较模拟与观测的方法需要配置观测序列。
