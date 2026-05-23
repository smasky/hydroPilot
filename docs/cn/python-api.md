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

- `X` — 设计参数值的列表或 numpy 数组，顺序与配置中 `parameters.design` 列表的定义顺序一致。一维数组执行单次评估；形状为 `(样本数, 输入数)` 的二维数组执行批量运行。单次评估也支持以字典方式按名称传入：`model.run({"CN2": 72.5, "ALPHA_BF": 0.3, "GW_DELAY": 120})`。
- 返回 `BatchRunResult`。批量运行时，`result.objs` 的形状为 `(样本数, 目标数)`。

每次评估的内部流程：
1. 从 `basic.projectPath` 复制项目到 `basic.workPath` 下的临时实例目录。
2. 将设计值变换为物理参数并写入模型输入文件。
3. 在项目副本中执行模型命令（`basic.command`）。
4. 提取模拟输出并进行评估（目标、约束、诊断）。
5. 结果与产物归档，项目副本被释放（或当 `keepInstances: true` 时保留）。

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
| `xLabels` | `list[str]` | 设计参数的名称列表 |
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

### 使用示例

```python
result = model.run([72.5, 0.3, 120])
print(result.objs)     # 例如 [[0.78]]
print(result.X)        # [[72.5, 0.3, 120.0]]
```

单次运行时，数组维度中 `样本数 = 1`。

---

## `UQPyLAdapter`

将 `SimModel` 包装为 UQPyL `Problem`，用于 UQPyL 的优化和分析算法。

```python
from hydropilot.integrations import UQPyLAdapter

adapter = UQPyLAdapter("path/to/config.yaml")
```

### 说明

`UQPyLAdapter` 继承自 `UQPyL.problem.Problem`，内部委托给 `SimModel`。它从 hydroPilot 配置中提取 UQPyL 问题定义（`nInput`、`nObj`、`nCon`、边界、变量类型、目标方向）。

### 上下文管理器

```python
with UQPyLAdapter("config.yaml") as adapter:
    result = adapter.evaluate(X)
    objs = result.objs
```

### 方法

#### `evaluate(X)`

```python
result = adapter.evaluate(X)
objs = result.objs
cons = result.cons
```

运行模型并返回 `UQPyL.problem.Eval` 对象。与调用 `evaluate()` 的 UQPyL 算法兼容。

#### `objFunc(X)`

```python
objectives = adapter.objFunc(X)
```

仅返回目标值（NumPy 数组）。与调用 `objFunc(X)` 的 UQPyL 优化器兼容。

#### `conFunc(X)`

```python
constraints = adapter.conFunc(X)
```

仅返回约束值（NumPy 数组）。如果配置中未定义约束则返回 `None`。

### 适用范围

适配器提供基础的 UQPyL `Problem` 接口：问题定义、返回 `Eval` 的评估接口以及目标/约束访问器。它不实现 UQPyL 专属的分析方法（敏感性分析、代理建模等）。对于高级 UQPyL 工作流，可将适配器作为 `Problem` 使用，并直接调用 UQPyL 自身的分析函数。

### 示例：使用适配器

```python
from hydropilot.integrations import UQPyLAdapter

with UQPyLAdapter("config.yaml") as adapter:
    # 评估一个参数向量
    result = adapter.evaluate(X)
    objs = result.objs
    cons = result.cons

    # 或分别获取目标与约束
    objs = adapter.objFunc(X)
    cons = adapter.conFunc(X)
```

适配器可传递给任何接受 `Problem` 实例的 UQPyL 算法。

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
