# UQPyL 集成

HydroPilot 提供 `UQPyLAdapter`，将 HydroPilot 配置桥接到 UQPyL 优化工作流中。适配器把 `SimModel` 包装为 UQPyL 的 `Problem`，因此任何 UQPyL 算法都可以直接优化 HydroPilot 配置中定义的参数。

## 安装

安装带 UQPyL 支持的 HydroPilot：

```bash
pip install -e ".[uqpyl]"
```

本工作区在 `py312` conda 环境下验证：

```bash
conda run -n py312 python -m pytest tests/test_public_imports.py -q
```

UQPyL 需单独安装。本仓库当前完成验证的集成目标，是在 2026 年 5 月 23 日验证时 PyPI 上可安装的最新发布版：`UQPyL==2.1.6`。

## 导入

```python
from hydropilot.integrations import UQPyLAdapter
```

## 工作原理

`UQPyLAdapter` 继承自 `UQPyL.problem.Problem`。它从 HydroPilot 配置创建 `SimModel`，并向 `Problem` 注册一个私有的评估回调：

```python
class UQPyLAdapter(Problem):
    def __init__(self, cfgPath: str):
        self.model = SimModel(cfgPath)
        super().__init__(
            nInput=self.model.nInput,
            nObj=self.model.nOutput,
            nCon=self.model.nConstraints,
            varType=self.model.varType,
            varSet=self.model.varSet,
            ub=self.model.ub,
            lb=self.model.lb,
            xLabels=self.model.xLabels,
            optType=self.model.optType,
            evaluate=self._evaluate,
        )

    def _evaluate(self, X):
        result = self.model.run(X)
        return Eval(objs=result.objs, cons=result.cons)
```

适配器将 HydroPilot 的配置结构映射到 UQPyL 的 `Problem` 构造参数：

| HydroPilot 配置 | UQPyL Problem 参数 |
|---|---|
| 设计参数数量 | `nInput` |
| 目标数量 | `nObj` |
| 约束数量 | `nCon` |
| `type: discrete` 参数 | `varType` + `varSet` |
| 设计参数边界 | `ub` / `lb` |

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

`evaluate(X)` 返回 `UQPyL.problem.Eval` 对象，包含 `.objs` 和 `.cons` 属性。

`X` 的格式：

- **一维数组** — 单个参数向量，形状 `(输入数,)`。适配器内部处理并返回单行结果。
- **二维数组** — 参数向量批次，形状 `(样本数, 输入数)`。每行对应一次评估。

继承而来的 `objFunc(X)` 和 `conFunc(X)` 访问器同样可用，返回与 `evaluate(X).objs` / `.cons` 相同的数组。

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
