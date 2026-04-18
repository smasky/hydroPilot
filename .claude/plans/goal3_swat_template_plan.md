# SWAT 模板样板化收口方案（目标3子方案）

## Context

本方案用于承接 `dev_plan1.md` 的目标 3，只聚焦一件事：把当前已经可运行的 SWAT 模板，继续收口成未来新模型可复制的标准样板。

当前目标 1、2 已经完成第一阶段落地：
- general config 已显式支持 `writerType` / `readerType`
- runtime 已通过最小 registry 分发 writer / reader
- SWAT 参数链路已经具备 `discovery / library / builder / template` 的基本分层

因此，目标 3 现在不再是“补功能”，而是“收边界、立样板”。重点不是继续增强 SWAT 特性，而是把它整理成一个后续 VIC / APEX / 其他模型都能参考的模板实现范式。

---

## 一、目标定位

目标 3 的完成标准不是“SWAT 能跑”，而是：

1. `discovery / library / builder / template` 四层职责清楚
2. template 层主要负责编排，不长期承载大段模型细节解析
3. library 被明确定位为“模型知识层”，当前以输入参数知识为主，但不排斥未来扩展输出知识
4. 模板最终产物始终是可独立运行的 general config
5. SWAT 模板具备足够清楚的结构和测试，可以作为未来模板参考实现

---

## 二、现状判断

### 已完成部分

当前 SWAT 模板已经具备以下基础：

- `hydro_pilot/templates/swat/discovery.py`
  - 已能从 SWAT 工程中抽取时间范围、子流域、HRU、文件映射等元数据
- `hydro_pilot/templates/swat/library.py`
  - 已能提供参数知识库与默认参数定义
- `hydro_pilot/templates/swat/builder.py`
  - 已能完成参数过滤、位置展开、physical/design 构建
- `hydro_pilot/templates/swat/template.py`
  - 已能调度 discovery、builder，并补齐 `readerType`、`writerType`、`reporter` 等 general config 必要字段

这说明 SWAT 已经不是零散实现，而是具备样板雏形。

### 仍需收口的问题

但从“未来模板参考实现”的标准看，当前还有三个问题：

1. `template.py` 仍然承担了较多 series 语义解析逻辑
   - 包括 `output.rch/sub/hru` 判定
   - `calcSwatOutputRows()` 的调用条件判断
   - `size` 自动回填

2. `ModelTemplate` 的约束还偏弱
   - 目前接口已经存在，但“模板只产 general config、不接触 runtime I/O 细节”的边界还主要靠约定维持

3. 模板层测试还不够聚焦
   - 当前有端到端样例，但还缺 discovery / builder / series 解析 / build_config 这些定向测试

---

## 三、推荐方案

### 1. 保持四层框架不变

目标 3 当前仍按以下四层完成：

- `discovery`
- `library`
- `builder`
- `template`

这是当前最稳的框架，不建议这一步再拆出更多概念层，以免目标 3 范围扩散。

### 2. 将 library 定位为“模型知识层”

现阶段 `library` 仍以**输入参数知识**为主，这是合理的。

但设计上不要把它锁死成“只允许参数知识库”。更合适的定位是：

- 当前：以 input knowledge 为主
- 后续：允许逐步纳入 output knowledge

也就是说，目标 3 当前不要求新增完整 output library，但要保留这个演进方向，避免把 `library.py` 设计成只能容纳参数定义的狭义结构。

### 3. 优先收 template 的 series 逻辑

目标 3 下一步最值得做的，不是继续动参数 builder，而是收口 `template.py` 中的 series 解析逻辑。

推荐把这部分逐步下沉成独立的内部解析单元，例如：

- `variables.py`
- `series_resolver.py`
- 或 builder 内专门的 series resolve 函数

这一步的目标不是增加抽象层，而是让：

- `template.py` 更接近 orchestration
- 输出变量语义不再散落在 template 主流程中
- 未来新模型模板可以照着同样结构组织 series 解析逻辑

### 5. 明确子模型 template 不是兜底层

目标 3 在收口过程中，还应明确一条模板边界原则：

- SWAT template 只处理自己明确识别并承诺支持的 SWAT 语义
- 对未命中 SWAT 规则、但 general 可处理的字段，应原样保留并交给 general
- template 不应提前吞掉或猜测不属于自身职责的字段

这条原则的直接作用是：

- template 负责精准翻译，而不是隐式兜底
- general config 继续作为统一协议边界
- 未来其他模型模板也能遵循同样的收口方式

---

## 四、建议改动点

### 关键文件

- `hydro_pilot/templates/base.py`
- `hydro_pilot/templates/swat/template.py`
- `hydro_pilot/templates/swat/builder.py`
- `hydro_pilot/templates/swat/discovery.py`
- `hydro_pilot/templates/swat/library.py`
- 如需要可新增：
  - `hydro_pilot/templates/swat/variables.py`
  - 或 `hydro_pilot/templates/swat/series_resolver.py`

### 推荐动作

1. 在不破坏现有行为的前提下，把 SWAT series 自动展开逻辑从 `template.py` 中收出来
2. 保持 `library.py` 作为模型知识入口，当前继续以参数知识为主
3. 若 output knowledge 开始沉淀，优先放到 `variables.py` 或独立 resolver，而不是直接把所有规则塞进参数库
4. 让 `template.py` 最终主要承担：
   - 调 discovery
   - 调 library/builder
   - 调 series resolver
   - 补齐 general config 默认字段
   - 输出最终 general config

---

## 五、推荐实施顺序

### Step 1
先冻结当前四层框架命名：`discovery / library / builder / template`

### Step 2
抽离 `template.py` 中的 series 解析逻辑，使 template 变薄

### Step 3
明确 `library` 的定位是“模型知识层”，当前先不强行拆 input/output 两套文件

### Step 4
补 discovery / builder / series resolver / build_config 的定向测试

### Step 5
用 monthly complex 样例做一次模板层回归，确认 general config 输出不回退

---

## 六、验证策略

### 1. 结构验证
- `template.py` 是否主要承担编排，而非承载大段模型细节解析
- `discovery / library / builder` 是否各自边界清晰

### 2. 模板层测试
- `discover_swat_project()` 的 discovery 测试
- `buildSwatParams()` 的 builder 测试
- SWAT series 解析逻辑测试
- `SwatTemplate.build_config()` 的最终 general config 测试

### 3. 回归验证
- `pytest`
- `python scripts/test_monthly_complex.py`
- 检查导出的 `_general.yaml` 中 `writerType` / `readerType` / `reporter` 是否仍稳定存在

---

## 七、与 dev_plan1 的关系

本方案是 `dev_plan1.md` 中“目标 3：整理 SWAT 模板为标准样板”的子方案。

`dev_plan1` 负责描述第一阶段总体目标；本文件负责说明目标 3 在当前阶段的具体收口方向、实施顺序与验证方式。
