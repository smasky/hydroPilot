# Context

用户希望先做 hydroPilot 的整体路线梳理，而不是立刻实现某个具体功能。目标是基于当前代码真实状态，给出后续开发优先级和阶段划分，便于后续按阶段推进。

从现有代码看，主执行链路已经打通：配置加载 → 参数写入 → 模型执行 → 结果提取 → 指标评估 → 结果记录。当前框架的核心价值在于主流程已经稳定，但大部分扩展点仍停留在“单一实现”阶段：writer 目前主要是 fixed-width，reader 目前主要是 text，runner 目前主要是 subprocess，模板侧目前 SWAT 最完整。因此路线规划应优先围绕“补齐可验证的基础能力”而不是过早铺开过多模型或抽象。

## 推荐路线

### 阶段 1：先补测试基线，固化现有主链路

**目标**
- 为当前已经存在的核心能力建立可靠回归保护，降低后续扩展 reader / writer / template / evaluator 时的回归风险。

**涉及模块**
- `hydro_pilot/config/loader.py`
- `hydro_pilot/params/manager.py`
- `hydro_pilot/params/writers/fixed_width.py`
- `hydro_pilot/series/readers/text_reader.py`
- `hydro_pilot/series/extractor.py`
- `hydro_pilot/evaluation/evaluator.py`
- `hydro_pilot/templates/swat/variables.py`
- `tests/`

**建议复用的现有实现**
- `load_config()` 的 general/template 双路径
- `read_text_extract()` 的文本提取逻辑
- `FixedWidthWriter.register_param()` / `set_values_and_save()` 的写入逻辑
- `Evaluator.evaluate_all()` 中 fatal / warning 分流逻辑

**产出**
- 覆盖配置解析、文本提取、fixed-width 写入、derived 失败分级、SWAT 输出行号计算的单元测试
- 明确哪些现有 `scripts/test_*.py` 只是手工验证脚本，哪些要转成正式测试

**验证**
- 运行 `pytest`
- 可按模块跑单测，例如 `pytest tests/test_xxx.py -k case_name`
- 对 SWAT 相关逻辑优先做纯函数级验证，避免一开始就依赖真实模型运行环境

### 阶段 2：补齐“可扩展点”的注册与选择机制

**目标**
- 把当前“接口存在但实现绑定较死”的位置，整理成真正可插拔的扩展点，为后续新增 reader / writer / runner 做准备。

**涉及模块**
- `hydro_pilot/adapter/adapter.py`
- `hydro_pilot/runner/base.py`
- `hydro_pilot/runner/subprocess_runner.py`
- `hydro_pilot/series/readers/base.py`
- `hydro_pilot/params/writers/base.py`
- `hydro_pilot/config/specs.py`
- `hydro_pilot/templates/base.py`

**建议方向**
- 明确 readerType / writerType / runnerType 在配置中的入口与装配位置
- 避免继续把 `SubprocessRunner`、`TextReader`、`FixedWidthWriter` 写死在主装配链路中
- 保持 `SimModel -> ModelAdapter` 主流程不变，只替换装配策略

**产出**
- 清晰的组件注册/分发规则
- 配置层面对不同实现的选择入口
- 保持现有 SWAT/general 配置兼容的装配方案

**验证**
- 现有测试继续通过
- 至少能在不改主流程的情况下切换一个 mock/替代实现用于验证装配链路

### 阶段 3：优先扩展最缺的通用 I/O 能力

**目标**
- 在框架已经可插拔之后，优先补齐最能提升多模型适配能力的 reader / writer 实现。

**优先顺序建议**
1. 新 writer
2. 新 reader
3. 新 runner

**原因**
- 当前参数写入和结果提取是模型接入时最容易成为瓶颈的部分
- runner 目前 subprocess 已经能覆盖很多本地可执行模型，优先级可略低于 reader / writer

**涉及模块**
- `hydro_pilot/params/writers/`
- `hydro_pilot/series/readers/`
- `hydro_pilot/runner/`

**建议产出**
- 一个新的通用 writer（例如 key-value 类配置文件）
- 一个新的通用 reader（例如结构化文本或 NetCDF，按实际目标模型优先）
- 配套示例配置与测试样例

**验证**
- 为每个新实现提供最小可运行样例
- 用示例 YAML 覆盖从配置加载到组件装配的端到端流程

### 阶段 4：增强评估层能力，补齐水文常用指标

**目标**
- 让 evaluation 层更贴近水文建模常见需求，提高框架的可用性，而不是只停留在基础 RMSE/MSE/R2。

**涉及模块**
- `hydro_pilot/evaluation/func_manager.py`
- `hydro_pilot/evaluation/evaluator.py`
- 可能涉及 `hydro_pilot/config/specs.py`

**建议方向**
- 优先补齐 README / 项目上下文中已经多次提到的常用水文指标
- 保持 builtin function 与 external function 的统一调用方式
- 明确 series / derived / objective / diagnostic 的依赖边界，避免增加函数后让错误传播更难追踪

**产出**
- 新增常用指标函数
- 对应测试用例
- 一个能展示多 derived、多 objective 的示例配置

**验证**
- 针对每个指标做数值级测试
- 验证 derived 出错时 fatal / warning 的既有规则不被破坏

### 阶段 5：围绕模板系统扩展新模型接入能力

**目标**
- 在底层 I/O 和评估能力稳定后，再推进新的模型模板，避免模板层为弥补底层缺口而承担过多特殊逻辑。

**涉及模块**
- `hydro_pilot/templates/`
- `hydro_pilot/templates/swat/`
- `hydro_pilot/config/loader.py`

**建议方向**
- 先把 SWAT 模板继续打磨成“模板样板间”
- 总结 discovery / parameter library / builder / variable resolving 的共性接口
- 再抽象到下一个模型（如 APEX/HBV/VIC）

**产出**
- SWAT 模板能力边界说明
- 新模型模板的最小骨架
- 一个从 simplified config 展开到 general config 的完整样例

**验证**
- 模板展开结果可落盘为 `_general.yaml` 并可直接运行
- 模板模式与 general 模式在内部配置结构上保持一致

## 关键判断

本次路线建议的核心不是“先支持更多模型”，而是：
1. 先用测试锁住现有主链路
2. 再把扩展点从单一实现提升为真正可插拔
3. 然后补 reader / writer / evaluation 这些高复用能力
4. 最后再扩大模板和模型覆盖面

这样做的原因是，当前仓库已经有较清晰的分层，但很多层级仍只有一个具体实现。若现在直接扩模型，后续大概率会把模型差异硬编码回主链路或模板层，反而削弱架构价值。

## 关键文件

规划执行时应优先关注这些文件：
- `hydro_pilot/sim_model.py`
- `hydro_pilot/adapter/adapter.py`
- `hydro_pilot/config/loader.py`
- `hydro_pilot/config/specs.py`
- `hydro_pilot/params/manager.py`
- `hydro_pilot/params/writers/fixed_width.py`
- `hydro_pilot/series/extractor.py`
- `hydro_pilot/series/readers/text_reader.py`
- `hydro_pilot/evaluation/evaluator.py`
- `hydro_pilot/evaluation/func_manager.py`
- `hydro_pilot/reporting/reporter.py`
- `hydro_pilot/templates/swat/template.py`
- `tests/`

## 验证与推进方式

- 第一轮只做规划审批，不改代码
- 落地时建议按“阶段 1 → 阶段 2 → 阶段 3”顺序推进，不要并行大范围铺开
- 每推进一个阶段，都至少补一组对应测试和一个最小配置样例
- 端到端验证建议结合：
  - `pytest`
  - 单测定向运行：`pytest tests/test_xxx.py -k case_name`
  - 示例配置加载验证
  - 必要时使用现有 `scripts/test_*.py` 做人工回归
