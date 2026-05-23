# SWAT+ 支持现状

这份文档只做一件事：总结当前代码库里，hydroPilot 对 SWAT+ 已经实现到了什么程度。

它不是路线宣言，而是一份阶段性事实清单。

## 当前结论

`version: swatplus` 现在已经具备独立模板主线，包含：

- 模板展开
- 工程发现
- 参数数据库支持
- 基于 `calibration.cal` 的参数写入
- Tier 1 流量序列抽取
- `apply` 路径与 `session` 路径的初始化行为对齐

同时，SWAT+ 和 SWAT 2012 仍然保持为两套独立模板，没有合并模型逻辑。

## 已实现部分

### 1. 模板层

当前已经实现：

- `version: swatplus`
- 基于真实工程文件的 SWAT+ 项目发现
- SWAT+ 专属前置校验
- 展开为标准 `version: general`

当前模型入口在：

- [`src/hydropilot/models/swatplus/template.py`](/Users/smasky/Desktop/hydroPilot/hydroPilot/src/hydropilot/models/swatplus/template.py)

### 2. 参数写入主路线

当前已经实现：

- SWAT+ 参数写入统一指向 `calibration.cal`
- 模板输出 `writerType: formatted_text`
- skeleton 部署复用共享初始化边界
- 源工程里可以不存在 `calibration.cal`
- `apply_design` / `apply_physical` 现在也会在写值前先初始化 skeleton

这部分最关键的用户侧变化是：

- 用户不再需要从运行时角度思考如何直接修改 `parameters.bsn`、`hydrology.hyd` 这类源文件

### 3. 参数数据库

当前数据库分组如下：

| 分组 | 文件 | 状态 |
|---|---|---|
| A | `parameters.bsn` | 已注册，可生成 calibration 记录 |
| B | `hydrology.hyd` | 已注册，filter 规格会保留 |
| C | `hyd-sed-lte.cha` | 数据库条目已就绪，更深的 calibration 展开仍待继续 |
| D | `soils.sol` | 数据库条目已就绪，更深的 calibration 展开仍待继续 |

现在的 SWAT+ 参数库已经比最初 MVP 宽很多，但并不是所有参数组都已经在 `calibration.cal` 路线上接到同样深。

### 4. Series 层

当前已经实现：

- SWAT+ 输出发现与抽取逻辑
- 基于 `swatplus_db.yaml` 的 file + variable 查找
- `aa / yr / mo / da` 频率处理
- 对 SWAT+ 真实命名 `_mon.txt / _day.txt` 的支持

目前已经补齐的 Tier 1 流量路线包括：

- `hydout`
- `hydin`
- `basin_wb`
- `channel_sd`

频率覆盖包括：

- `aa`
- `yr`
- `mo`
- `da`

### 5. 本机真实验证

当前已经在这台机器上完成验证：

- SWAT+ 源码可以用 `gfortran` 本机编译
- 编译后的二进制能在 `refdata/Ames_sub1` 上成功运行
- hydroPilot 能基于 `version: swatplus` 生成真实 SWAT+ 输出目录
- `apply` 路径与 `session` 路径的初始化语义已经对齐

## 部分实现、尚未完全闭环的部分

下面这些部分已经有基础，但还不是最终完成态。

### 1. filter 语义

当前状态：

- SWAT+ 模板允许写 `filter`
- filter 规格会保留在 physical 条目里
- discovery 已经能解析 `lu_mgt`、`soil`、`hydro_name`

尚未完成：

- 展开为原生 `calibration.cal` 条件语法
- 展开为最终对象列表，或其他真正落到 SWAT+ calibration targeting 的形式

### 2. 不同参数组的 calibration 支持深度

当前状态：

- `parameters.bsn` 和 `hydrology.hyd` 是当前接线最完整的两组

尚未完成：

- `hyd-sed-lte.cha` 的完整 calibration 记录展开策略
- `soils.sol` 的完整 calibration 记录展开策略

### 3. 真实工程覆盖度

当前状态：

- `Ames_sub1` 已经可以作为真实验证样例使用

仍然需要：

- 更多真实工程
- 更多不同工程结构
- 更多 calibration 开/关组合
- 更强的“参数写入后是否真的改变结果”的实证验证

## 当前还不能宣称的内容

按目前代码状态，还不能直接宣称：

- 已完整覆盖 SWAT+ 原生 calibration 条件语法
- 已对所有 SWAT+ 参数家族做到完全对等支持
- 已在大量 SWAT+ 工程上完成生产级验证
- 已完成 filter 到最终 calibration targeting 的全部展开

## 下一阶段最自然的实现优先级

如果继续从当前状态往下推进，最自然的顺序是：

1. 完成 filter 到最终 SWAT+ calibration targeting 语义的展开
2. 深化 `hyd-sed-lte.cha` 与 `soils.sol` 的 calibration 支持
3. 在真实 SWAT+ 工程上验证“写入后结果可观测变化”
4. 把 series 支持继续扩到 Tier 1 流量之外

## 参见

- [SWAT+ 模板](../templates/swatplus.md)
- [SWAT+ `calibration.cal` 写入链路](swatplus-calibration-cal.md)
- [SWAT+ `calibration.cal` 用户指南](swatplus-calibration-cal-user-guide.md)
- [SWAT+ 流量抽取指南](swatplus-flow-extraction.md)
