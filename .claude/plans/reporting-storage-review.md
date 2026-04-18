# Context

用户这次要规划的重点，不是整个 hydroPilot 的阶段路线，而是专门评估“现有结果存储方式从后期演进来看是否够用”。当前实现由 `SimModel` 在每次运行时把 `context` 提交给 `RunReporter`，后者异步写入 `results.db`、`summary.csv`、`error.jsonl`、`error.log` 以及可选的 series CSV。规划目标应聚焦于：这套存储模型在后续规模扩大、分析需求增强、模型类型变多之后，是否还能支撑；如果不够，应该优先改哪里、怎么改、改到什么程度。

## 现状判断

### 当前方案的优点

现有存储设计在“本地实验驱动、单次运行可回溯、便于人工查看”这个层面是够用的：

- `summary.csv` 便于快速肉眼查看与导出
- `results.db` 便于后续程序化查询
- `error.jsonl` + `error.log` 同时照顾结构化记录和人工排障
- `series` 被单独放在 SQLite 表里，没有和 summary 强行混在一起
- `RunReporter` 通过后台线程异步写盘，避免主执行链路直接承担 IO 成本

对当前项目阶段来说，这是一套合理的“轻量本地结果仓库”。

### 从后期演进看，主要瓶颈

但从中长期看，这套方案有几个明显边界：

1. **summary 表是宽表，扩展成本高**  
   当前 `summary` 的列是在启动时根据 objectives / constraints / diagnostics / derived / X / P 动态拼出来的。只要实验结构变化，表结构就跟着变化。这对单次 run 没问题，但不利于跨实验、跨配置、跨模型做统一查询。

2. **series 数据以 BLOB 形式写入 SQLite，可回放但不可分析**  
   `series` 表现在只存 `(batch_id, run_id, series_id, data)`，其中 `data` 是 `float32` 字节流。优点是写入快、体积相对小；缺点是数据库层几乎不能直接做按时间步、按区段、按统计量的查询。后期如果要做“按时间段比较多个 run 的 hydrograph”之类分析，这种格式会成为瓶颈。

3. **缺少稳定的实验元数据层**  
   现在 backup 目录里会保存 config、副本和结果文件，但数据库本身没有清晰的 experiment / runset / config fingerprint / template version 等元信息表。后期如果用户需要比较“同一项目不同配置”“同一模型不同模板版本”的结果，当前结构会比较散。

4. **结果仓库是单次 runPath 级别隔离的，不是长期归档级设计**  
   每次 `SimModel` 运行都会生成一个新的 `tempRun/.../backup`。这适合一次实验内自洽，但不适合长期累积、统一检索、批量对比多个历史实验。

5. **reporter 配置能力偏少**  
   当前 `ReporterSpec` 只有 `flushInterval`、`holdingPenLimit`、`series`，能控制刷盘频率和导出哪些序列，但还不能表达：
   - 保存哪些元数据
- series 用哪种存储格式
- 是否保留全部 derived / warnings 上下文
- 是否输出面向后处理的标准化结果集

## 推荐结论

**结论不是“现有方案不行”，而是：**

- 作为当前阶段的本地执行结果存储，**够用**
- 作为后期面向“跨实验管理、统一分析、长期归档”的结果层，**还不够**

因此不建议现在推倒重做 reporter，而是建议按“保留现有轻量方案 + 增量补齐演进能力”的路线推进。

## 推荐规划

### 阶段 1：先补“结果元数据层”，不动核心写盘骨架

**目标**
- 让结果不只是“某次 run 产生的一堆文件”，而是可被长期识别、比较、追踪的实验记录。

**涉及文件**
- `hydro_pilot/reporting/reporter.py`
- `hydro_pilot/sim_model.py`
- `hydro_pilot/config/specs.py`

**建议复用的现有实现**
- `SimModel.create_run_queue()` 已经能确定 runPath / backupPath
- `RunReporter` 已经有 batch_id / run_id 的组织方式

**建议新增的元数据方向**
- experiment 级信息：创建时间、config 文件名、resolved general config 是否存在、模型/模板版本
- runset 级信息：本次 evaluate 的 batch_id、输入维度、目标数、约束数、parallel 配置
- config 指纹：原始配置路径、resolved 配置路径、可选 hash/fingerprint

**产出**
- 至少补一层稳定元数据表，而不是只靠目录结构表达上下文

**验证**
- 同一配置多次运行时，能够明确区分不同实验
- 不同配置运行时，能够在结果层直接知道差异来源

### 阶段 2：把 summary 从“动态宽表”提升为“稳定主表 + 扩展明细”

**目标**
- 保留当前 summary.csv / summary 表易读易导出的优点，同时降低后期 schema 演进压力。

**涉及文件**
- `hydro_pilot/reporting/reporter.py`

**建议方向**
- 保留当前 summary 导出作为“用户友好视图”
- 在数据库层增加更稳定的规范化结构，例如：
  - runs 主表：run 基本状态
  - scalar_values 明细表：`(run_id, key, value, kind)`
- 不强求立刻去掉宽表，但应避免未来所有分析都绑定在宽表 schema 上

**原因**
- objective / constraint / diagnostic / derived 会随着实验结构变化频繁增减
- 用动态列来承载长期演进的数据模型，后期会越来越难维护

**验证**
- 同一个 reporter 可以处理不同实验结构，而不依赖完全一致的列集合
- 后续分析代码可以不再写死列名

### 阶段 3：重审 series 的存储目标，区分“回放存档”和“分析查询”

**目标**
- 明确 series 到底主要服务什么用途，再决定是否升级存储格式。

**当前事实**
- 现在的 BLOB 存储很适合“保存序列，必要时读回来”
- 但不适合直接数据库查询分析

**建议判断标准**
- 如果后续 series 主要是用于结果留档和偶尔导出：当前 BLOB 方案可以继续保留
- 如果后续 series 需要支撑频繁比较、统计聚合、按时间切片查询：应增加面向分析的数据形态

**可选方向**
- 保留 SQLite BLOB 作为归档格式
- 额外增加可分析导出层，例如逐点展开表、专用 CSV、或更适合数组数据的文件格式

**规划建议**
- 这一阶段先做需求确认，不必马上实现复杂存储重构
- 先弄清楚后期最常见的后处理动作是什么，再决定是否拆分存储

**验证**
- 能用真实分析场景检验：例如跨 run 比较某个序列、提取某时间窗统计量、导出作图

### 阶段 4：补 reporter 的配置表达能力

**目标**
- 让用户能显式声明“哪些结果要保留、以什么粒度保留、为了什么后处理场景保留”。

**涉及文件**
- `hydro_pilot/config/specs.py`
- `hydro_pilot/reporting/reporter.py`

**当前限制**
- `ReporterSpec` 只有 `flushInterval`、`holdingPenLimit`、`series`

**建议扩展方向**
- 是否保存全部 series / 仅保存选定 series
- 是否保存 physical parameters `P`
- 是否保存 derived 明细
- 是否生成面向分析的标准化导出文件
- 是否记录更完整的 warning / error 上下文

**验证**
- 配置层能明确表达不同实验的结果保留策略
- 不同规模实验可以选择不同的存储成本

## 推荐的规划顺序

1. **先补元数据层**
2. **再稳定数据库结构（主表 + 明细）**
3. **然后根据真实需求决定是否升级 series 存储形态**
4. **最后补 reporter 配置能力**

原因是：
- 元数据层是后续长期管理的基础
- summary 的结构问题是最早会影响扩展性的点
- series 存储是否要重构，必须由真实分析需求驱动，不能先拍脑袋设计

## 这次规划中最值得重点审查的文件

- `hydro_pilot/reporting/reporter.py`
- `hydro_pilot/sim_model.py`
- `hydro_pilot/config/specs.py`

必要时可连带关注：
- `hydro_pilot/config/loader.py`（若后续要把结果元数据与 resolved config 绑定）
- `hydro_pilot/evaluation/evaluator.py`（若后续要区分哪些 scalar 必须入库，哪些只需导出）

## 验证方式

这轮是设计评审，不改代码。后续若进入实现，建议按下面方式验证：

- 构造两个配置结构不同的实验，验证结果层是否仍可统一检索
- 检查同一 experiment 下多 batch / 多 run 的元数据是否完整
- 验证错误、warning、summary、series 是否还能保持现有可读性
- 针对 series 的真实后处理场景做一次演练，再决定是否升级存储格式
