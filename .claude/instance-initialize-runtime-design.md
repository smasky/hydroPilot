# `instance initialize` 运行时挂载设计草案

这份文档只回答一个问题：

- 公用的 `instance initialize` 阶段
- 应该挂在当前 runtime 链路的哪里

目标是：

1. 不破坏现在的分层
2. 不给 `swatplus` 开特权通道
3. 让后续 `formatted_text` 可以复用这个阶段

---

## 1. 先说结论

我现在更推荐的挂载位置是：

- **放在 runtime 服务层**
- 由 `ExecutionServices` 装配一个公用的 `instanceInitializer`
- 在 `Session` 创建 `Workspace` 之后、`Executor` 正式运行之前，对所有 `instance_*` 执行一次初始化

也就是：

```text
Session
  -> Workspace(cfg, cfg_path)
  -> ExecutionServices.from_config(cfg)
  -> instanceInitializer.initialize_all(workspace)
  -> Executor(...)
```

这条线的核心优点是：

- `Workspace` 仍然只管复制和回收目录
- `Executor.run()` 仍然只管批量运行
- 初始化成为一个独立、公用、一次性的 runtime 准备步骤

---

## 2. 为什么不建议挂在 `Workspace`

当前 `Workspace` 的职责很干净：

- 创建 `runPath`
- 复制 `instance_*`
- 归档输入
- 管理实例队列
- 回收实例目录

如果把初始化逻辑塞进去，会出现两个问题：

### 2.1 `Workspace` 会开始理解模型输入语义

这会让它从“目录/文件系统管理对象”变成“带模型准备逻辑的对象”。

这不太符合现在的分层。

### 2.2 `Workspace` 无法自然拿到 writer / builder 相关能力

初始化本质上更接近：

- 使用已经准备好的参数写入描述
- 初始化受管文件

这些能力都更靠近 `ExecutionServices`，不靠近 `Workspace`。

所以我不建议把接口挂在 `Workspace` 上。

---

## 3. 为什么不建议挂在 `Executor.run()`

如果放在 `Executor._run_one()` 或 `Executor.run()` 前面，也能做，但不理想。

原因有两个：

### 3.1 初始化是“一次性”的，不是“每次运行”的

`Executor.run(X)` 的语义是：

- 针对一批输入参数做模型运行

而 instance 初始化的语义是：

- 为运行实例准备静态文件骨架

这两者不是一个层次的事情。

### 3.2 会让运行阶段混入准备逻辑

你前面已经定了一个很重要的边界：

- 初始化阶段写 header / 骨架
- 运行阶段只改值

如果再把初始化挂回 `run()`，边界就又糊了。

所以它不应该挂在 `Executor.run()`。

---

## 4. 推荐挂在 `Session` 装配流程

当前 `Session` 链路是：

```text
Session.__init__
  -> Workspace(...)
  -> Executor(...)
  -> Reporter(...)
```

我建议改成：

```text
Session.__init__
  -> Workspace(...)
  -> ExecutionServices.from_config(cfg)
  -> instanceInitializer.initialize_all(workspace)
  -> Executor(..., services=services)
  -> Reporter(...)
```

也就是说：

- `ExecutionServices` 先装出来
- 初始化器用这些服务做实例级静态准备
- 准备完再进入正式执行器

这样逻辑顺序最自然。

---

## 5. 为什么放在 `ExecutionServices` 里更顺

因为初始化阶段本质上也属于“执行前服务”。

它和下面这些能力是同一类东西：

- `ParamWritePlan`
- `ParamApplier`
- `runner`
- `seriesExtractor`

只不过：

- `ParamApplier` 是每次运行都调用
- `instanceInitializer` 是 session 级只调用一次

所以最合适的做法是：

- 让 `ExecutionServices` 统一装配它
- 但由 `Session` 决定调用时机

这样职责分配非常清楚。

---

## 6. 最小接口建议

我建议新增一个很小的公用接口，例如：

```python
class InstanceInitializer:
    def initialize_all(self, workspace) -> None:
        ...
```

它的职责只做一件事：

- 对 `workspace.runPath` 下所有 `instance_*` 完成静态初始化

如果要更明确一点，也可以拆成：

```python
class InstanceInitializer:
    def initialize_instance(self, instance_path: str) -> None:
        ...

    def initialize_all(self, workspace) -> None:
        ...
```

但本质上都一样。

---

## 7. 它应该依赖什么

这个初始化器不应该自己解析配置、也不应该自己做模型发现。

它应该依赖已经准备好的 runtime 服务：

1. `cfg`
2. `ParamWritePlan`
3. 可能的 writer 初始化能力

也就是说，它不是重新发明一套模型准备逻辑，而是消费已经准备好的 general 写入描述。

---

## 8. 它不应该知道什么

为了保持通用性，这个初始化器本身不应该知道：

- 什么是 `swatplus`
- 什么是 `calibration.cal`
- 什么是 `header`

它更合理的角色应该是：

- 遍历所有 write tasks
- 找出哪些 writer 支持初始化
- 对每个 instance 调用对应 writer 的初始化逻辑

也就是说：

- 初始化器只调度
- 真正的初始化细节仍然在 writer 里

---

## 9. 更顺的职责切法

如果按这个方向，职责可以切成：

### 9.1 `builder`

负责：

- 生成 general `physical`

### 9.2 `ParamWritePlan`

负责：

- 聚合 write tasks

### 9.3 `InstanceInitializer`

负责：

- 遍历实例目录
- 调用支持初始化的 writer

### 9.4 `formatted_text`

负责：

- 初始化静态文本骨架
- 运行时回填动态值

这样整个责任链是顺的。

---

## 10. 一个最小伪代码

### 10.1 `ExecutionServices`

```python
@dataclass
class ExecutionServices:
    paramWritePlan: ParamWritePlan
    paramApplier: ParamApplier
    instanceInitializer: InstanceInitializer
```

### 10.2 `Session`

```python
class Session:
    def __init__(self, cfg, cfg_path: str):
        self.workspace = Workspace(cfg, cfg_path)
        self.services = ExecutionServices.from_config(cfg)
        self.services.instanceInitializer.initialize_all(self.workspace)
        self.executor = Executor(cfg, self.workspace, reporter=None, services=self.services)
```

### 10.3 `InstanceInitializer`

```python
class InstanceInitializer:
    def __init__(self, write_plan: ParamWritePlan):
        self.write_plan = write_plan

    def initialize_all(self, workspace) -> None:
        for instance_path in workspace.iter_instance_paths():
            self.initialize_instance(instance_path)

    def initialize_instance(self, instance_path: str) -> None:
        for task in self.write_plan.write_tasks.values():
            handler = task["handler"]
            if hasattr(handler, "initialize_file"):
                handler.initialize_file(instance_path, task)
```

这个伪代码表达的重点只有一个：

- 初始化是 runtime 公用阶段
- 但初始化行为由具体 writer 决定

---

## 11. 对现有代码的最小改动点

如果后面真做实现，我认为最小改动应该集中在这几处：

1. `runtime/services.py`
   - 装配 `instanceInitializer`

2. `runtime/session.py`
   - 在 `Workspace` 创建后调用初始化

3. `runtime/workspace.py`
   - 最多补一个“列出所有 instance 路径”的便捷方法
   - 不塞模型逻辑

4. `io/writers/base.py`
   - 给 writer 增加可选初始化能力接口

5. `formatted_text writer`
   - 实现初始化骨架写入

这样改动是顺的，不会把职责打乱。

---

## 12. 我现在的最终判断

当前最稳的挂法就是：

- **初始化阶段存在**
- **它是公用 runtime 阶段**
- **由 `Session` 在启动时触发**
- **由 `ExecutionServices` 提供初始化器**
- **由具体 writer 决定如何初始化文件**

这样：

- `Workspace` 不变脏
- `Executor` 不变重
- `swatplus` 不拿特权
- `formatted_text` 也能真正成为一个通用能力

