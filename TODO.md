# TODO

## SWAT+ 下一阶段 Backlog

当前 `swatplus` 已经完成：

- 独立模板链路
- `calibration.cal` 主写入路径
- `apply` / `session` 初始化对齐
- Tier 1 流量 series 支持
- 本机源码编译与 `Ames_sub1` 真实运行验证

因此，这里的 TODO 不再记录“主链路是否成立”，只保留下一阶段尚未完成的深水区工作。

---

## 1. calibration 语义未完成部分

- 将 `filter` 从“保留在 physical 条目里”继续展开到最终 SWAT+ calibration targeting 形式
- 明确落地 `calibration.cal` 中的原生 conditions / object targeting 策略
- 验证不同 filter 组合在真实 SWAT+ 工程中的实际作用范围

## 2. 参数组接线深度仍待补齐

- 完成 `hyd-sed-lte.cha` 的 calibration 记录展开策略
- 完成 `soils.sol` 的 calibration 记录展开策略
- 继续评估是否推进 `aquifer / reservoir` 组的真实文件证据与接线

## 3. 真实工程验证仍待增强

- 验证 hydroPilot 生成的 `calibration.cal` 被 SWAT+ 实际消费后，输出结果是否发生可观测变化
- 增加不止一个真实 SWAT+ 工程的联调样例
- 继续分析 `Osu_1hru` 运行期边界检查失败是否属于样例问题、编译检查导致的问题，还是源码本身的运行假设问题

## 4. series 覆盖继续扩展

- 在 Tier 1 流量之外，继续补更多 SWAT+ 输出系列
- 逐步扩展更多报告类型与更多频率组合

## 5. 文档与状态维护

- 当 `filter` 真正落成最终 calibration targeting 后，同步更新 SWAT+ 模板文档与用户指南
- 当更多参数组真正接上线后，同步更新 SWAT+ 支持现状文档
