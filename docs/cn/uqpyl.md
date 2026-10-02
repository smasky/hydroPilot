# UQPyL 集成

当前 HydroPilot 0.1.4 适配器依赖提供 `SimContext`、`SimulatorBase`、`ModelEvaluatorBase` 的 UQPyL 开发源码。PyPI 的 UQPyL 2.1.6 尚无这些接口；请安装匹配的源码版本，例如 `pip install -e /path/to/UQPyL`。SimModel 独立运行不受此限制。

HydroPilot 提供唯一的 `UQPyLAdapter`，将 `SimModel` 包装为 UQPyL 的 `ModelProblem`。适配器直接继承原生公开接口，支持完整评估，以及分开调用模拟、目标和约束。普通优化可以不配置观测序列。

## 安装

安装带 UQPyL 支持的 HydroPilot：

```bash
pip install -e ".[uqpyl]"
```

本工作区在 `py312` conda 环境下验证：

```bash
conda run -n py312 python -m pytest tests/test_public_imports.py -q
```

当前完成验证的集成目标为 `UQPyL==2.1.6`，包括 2026 年 10 月 1 日用于验证的本地 UQPyL 源码。

## 导入

```python
from hydropilot.integrations import UQPyLAdapter
```

## 工作原理

`UQPyLAdapter` 直接继承 `UQPyL.problem.ModelProblem` 的 `evaluate`、`simulate`、`simFunc`、`objFunc` 和 `conFunc`。它从 HydroPilot 配置创建 `SimModel`，向 UQPyL 提供问题定义和私有回调。

适配器通过 `SimulatorBase` 调用内部批量调度入口 `SimModel._runSimulation(X)`，返回 `SimContext` 子类。调度层为每个样本组合 `_apply`（参数变换和写入）与 `_simulate`（模型执行和序列提取），并持有同一工作副本直到提取结束。context 除了原生的 `sims`、`obs`、`mask`，还包含 `simulation`，保存 HydroPilot 的 X、P、全部模拟与观测序列，以及逐样本记录。这一阶段不计算指标。

目标和约束调用委托给内部的 `_post`，按请求计算对应块及其 derived 依赖。结果保存在该 context 自己的后处理状态中，共享 derived 和重复请求可复用已有计算，不再次运行模型。`SimModel.run(X)` 仍是 HydroPilot 自身的独立完整入口，组合模拟与全部后处理。

适配器将 HydroPilot 的配置结构映射到 UQPyL 的 `ModelProblem` 构造参数：

| HydroPilot 配置 | UQPyL ModelProblem 参数 |
|---|---|
| 设计参数数量 | `nInput` |
| 目标数量 | `nObj` |
| 约束数量 | `nCon` |
| `type: discrete` 参数 | `varType` + `varSet` |
| 设计参数边界 | `ub` / `lb` |
| 目标 / 约束 id | `objLabels` / `conLabels` |

有观测数据时，定义了 `obs` 的 `series` 会暴露给 UQPyL。适配器会构建：

| 字段 | 形状 | 说明 |
|---|---:|---|
| `obs` | `(n_time, n_series)` | 按列对齐的观测值 |
| `mask` | `(n_time, n_series)` | 缺失观测及观测长度补齐的位置为 `True`，不会随模拟结果变化 |
| `seriesLabels` | `list[str]` | 列顺序对应的序列 id |

没有观测数据时，适配器暴露全部配置的模拟序列，`obs` 和 `mask` 为 `None`，可用于普通优化；需要比较模拟与观测的校准方法仍须配置观测序列。两种模式都至少需要一条模拟序列。

模拟中的 NaN 只保留在对应样本的模拟结果中，不会修改 `obs` 或 `mask`，也不会影响同批次的其他样本或后续运行。序列提取时会记录 `SIM_NAN` warning，并由 reporter 写入错误日志；适配器对有效观测位置上的模拟 NaN 另外发出 `RuntimeWarning`，注明样本编号、序列和缺失数量。观测缺失或长度补齐位置上的 NaN 不触发适配器警告。

没有观测数据时，模拟 NaN 同样触发 `RuntimeWarning`，并保留在模拟输出中。

适配器不填补 NaN，也不自动删除日期后重新计算目标值。目标、约束和诊断仍遵循 HydroPilot 原有函数与 `on_error` 规则；直接使用模拟序列的 UQPyL 方法需按自身规则处理这些 NaN。

## 基础评估

调用 `evaluate(X)` 会走完整的 HydroPilot 运行时来执行参数向量或批次：

```python
import numpy as np
from hydropilot.integrations import UQPyLAdapter

X = np.array([
    [50.0, 0.5, 100.0],
])

with UQPyLAdapter("examples/test_monthly.yaml") as adapter:
    result = adapter.evaluate(X)
    print(result.objs)   # 目标值
    print(result.cons)   # 约束值
```

`evaluate(X)` 返回 `UQPyL.problem.Eval` 对象，包含 `.objs`、`.cons` 和 `.sims` 属性。

`X` 的格式：

- **一维数组** — 单个参数向量，形状 `(输入数,)`。适配器内部处理并返回单行结果。
- **二维数组** — 参数向量批次，形状 `(样本数, 输入数)`。每行对应一次评估。

原生接口如下：

| 方法 | 返回内容 |
|---|---|
| `evaluate(X, target=None)` | 包含目标、约束和模拟序列的 `Eval`；`target` 可选 `"objs"`、`"cons"` 或 `"sims"` |
| `simulate(X)` | 包含 `sims`、`obs`、`mask`，以及 `simulation` 中完整模拟数据的 context |
| `simFunc(X)` | 形状为 `(n_samples, n_time, n_series)` 的模拟数组 |
| `objFunc(X, context)` | 计算该 context 的目标及其依赖；已计算时复用结果 |
| `conFunc(X, context)` | 计算该 context 的约束及其依赖；未配置约束时返回 `None` |

`evaluate(X)` 执行模拟和全部后处理，诊断结果保存到归档。`target="objs"` 或 `"cons"` 只计算对应块及其依赖；`target="sims"` 跳过后处理。每次 `evaluate` 都启动新的模拟。`flattenSim`、`flattenObs`、`flattenMask` 也直接继承原生实现。

分开调用时，可以继续使用之前的 context：

```python
with UQPyLAdapter("config.yaml") as problem:
    contextA = problem.simulate(XA)
    contextB = problem.simulate(XB)
    objA = problem.objFunc(XA, contextA)  # B 运行后，仍读取 A 的目标值
    objB = problem.objFunc(XB, contextB)
    physicalA = contextA.simulation.P
```

context 必须由同一个适配器返回，且 `X` 必须与产生它的参数相符。参数不匹配、另一适配器的 context、手工构造的 `SimContext` 都会触发 `ValueError`，因为无法对应到这次 HydroPilot 结果。后续模拟不会使已有 context 失效。

模拟与后处理分别向异步 reporter 提交独立快照，更新同一个 `(batch_id, run_id)` 记录。重复后处理不增加评估次数；先提交 SQLite，再从已提交数据导出 CSV 和错误日志。只调用模拟也能保存记录，未计算指标保留 pending 状态。具体见[归档配置](configuration-reference.md#reporter--输出持久化)。

## 与 UQPyL 优化器配合使用

从 UQPyL 优化分组中导入算法，创建实例，然后调用 `run(problem, seed=...)`：

```python
from UQPyL.optimization.soea import GA
from hydropilot.integrations import UQPyLAdapter

with UQPyLAdapter("examples/test_monthly.yaml") as problem:
    algorithm = GA()
    algorithm.run(problem, seed=42)
```

算法从适配器中读取问题的边界、类型和目标，在优化过程中内部调用 `evaluate()`。

其他算法分组包括用于多目标优化的 `UQPyL.optimization.moea`。

## 与 UQPyL 校准方法配合使用

同一个 `UQPyLAdapter` 也可直接用于需要模拟序列和观测序列的校准方法，例如 GLUE 和 SUFI2：

```python
import numpy as np
from UQPyL.calibration import GLUE, SUFI2
from hydropilot.integrations import UQPyLAdapter

X = np.array([
    [50.0, 0.5, 100.0],
    [65.0, 0.3, 120.0],
])

with UQPyLAdapter("examples/test_monthly.yaml") as problem:
    glue_result = GLUE(metric="rmse").run(problem, X, threshold=0.1)
    sufi2_result = SUFI2().run(problem, X, eliteSize=2)
```

返回结果中的 `result.sims` 形状为 `(n_samples, n_time, n_series)`。如果配置中有 `flow`、`tn` 两条观测序列，那么 `problem.seriesLabels == ["flow", "tn"]`。

## 生命周期

使用完毕后务必关闭适配器以释放运行时资源：

```python
# 上下文管理器（推荐）
with UQPyLAdapter("config.yaml") as problem:
    algorithm.run(problem, seed=42)

# 显式关闭
adapter = UQPyLAdapter("config.yaml")
try:
    algorithm.run(adapter, seed=42)
finally:
    adapter.close()
```

上下文管理器在退出时调用 `close()`，该方法会关闭底层的 `SimModel` 会话并清理临时工作区目录。

## 适用范围与局限性

`UQPyLAdapter` 是桥接层，不是分析库：

- **HydroPilot 负责**：配置加载、参数写入、模型执行、序列提取、目标/约束评估。
- **UQPyL 负责**：优化算法、敏感性分析、代理建模以及所有其他高级 UQPyL 工作流。
- **HydroPilot 不提供**：UQPyL 算法实现、UQPyL 分析方法，或任何关于 UQPyL 优化器收敛行为的保证。

有关本集成指南范围之外的 UQPyL 文档，请直接参考 UQPyL 项目。

## 参见

- [Python API](python-api.md) — `SimModel` 与 `BatchRunResult` 参考。
- [配置参考](configuration-reference.md) — 所有传入适配器的配置字段。
- [示例](examples.md) — 可用于 UQPyL 优化的示例配置。
