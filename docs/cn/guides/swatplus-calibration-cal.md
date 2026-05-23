# SWAT+ `calibration.cal` 写入链路

本文说明：当使用 `version: swatplus` 时，hydroPilot 现在是如何通过 `calibration.cal` 写入 SWAT+ 参数的。

## 现在的写法和之前有什么不同

现在的 SWAT+ 模板在运行时不再直接回写 `parameters.bsn`、`hydrology.hyd` 这类源参数文件。

它改成了另一条主路径：

1. 先把用户配置解析成物理层的标定记录
2. 为每个运行实例生成一份 `calibration.cal` 骨架
3. 运行时只往这些记录的 `VAL` 字段里写入当前参数值

也就是说，SWAT+ 现在走的是单文件 `calibration.cal` 标定路线；SWAT 2012 仍然保持自己的直接写文件路线，两者没有混在一起。

## 整体流程

当前写入链路可以概括为：

```text
version: swatplus
  -> SwatPlusTemplate.build_config()
  -> buildSwatPlusParams()
  -> 生成指向 calibration.cal 的 formatted_text physical 条目
  -> ParamWritePlan
  -> 实例初始化阶段写入 calibration.cal 骨架
  -> FormattedTextWriter 在运行时回填 VAL 列
```

## 展开后的 physical 长什么样

模板展开后，每个 SWAT+ physical 参数都会指向同一个文件：

```yaml
writerType: formatted_text
file:
  name: calibration.cal
  row: 5
  col: 30
  width: 16
  precision: 6
```

这里的含义是：

- `name` 永远是 `calibration.cal`
- `row` 表示这个物理参数对应哪一条标定记录
- `col` 指向 `VAL` 字段
- `width` 和 `precision` 复用通用 `formatted_text` writer 的契约

## `mode` 是怎么映射的

SWAT+ 模板会把 hydroPilot 的 `mode` 翻译为 SWAT+ 的 `CHG_TYPE`：

| hydroPilot mode | SWAT+ `CHG_TYPE` | 含义 |
|---|---|---|
| `v` | `absval` | 直接赋绝对值 |
| `a` | `abschg` | 做绝对增减 |
| `r` | `pctchg` | 做百分比变化 |

这层映射发生在 `models/swatplus` 内部，不会灌进通用 writer。

## skeleton 是怎么生成的

源工程目录里不要求事先存在 `calibration.cal`。

实例初始化阶段会做这几步：

1. 先把源 project 复制到每个 instance 目录
2. 再把模板生成的 skeleton 写入 `instance_x/calibration.cal`
3. 然后针对这份新生成的文件回放延迟注册
4. 真正运行时只更新 `VAL` 列

这样做的好处是：

- general 层只知道“有些 `formatted_text` 任务带 skeleton”
- skeleton 具体长什么样，仍然由 `swatplus` 模型层决定

## 目前已经完成了什么

当前已经落地的能力包括：

- SWAT+ 模板输出 `writerType: formatted_text`
- 参数写入统一汇总到 `calibration.cal`
- skeleton 基于 resolved physical 列表生成
- 即使源 project 没有 `calibration.cal`，主链路也能正常初始化
- 行号、记录数、参数顺序、`CHG_TYPE` 都和同一份 resolved physical 列表保持一致

## 还有哪些没做完

当前这条路线是一个有意收敛过的 MVP，下面这些还没完成：

- 把 SWAT+ `filter` 进一步展开成原生 calibration 条件或对象列表
- 继续扩 still pending 的参数组 calibration 支持
- 用更多真实 SWAT+ 工程和可执行文件做端到端验证

目前 `filter` 只是在 SWAT+ physical 条目里被保留下来，还没有真正展开成最终的 `calibration.cal` 条件行。

## 一个直观例子

如果用户写的是：

```yaml
parameters:
  design:
    - name: esco
      bounds: [0.0, 1.0]
  physical:
    - name: esco
      mode: v
```

那 hydroPilot 在运行时不会直接去改 `hydrology.hyd`。

它会先在 `calibration.cal` 里生成一条语义上类似这样的记录：

```text
esco         absval         <VAL> ...
```

然后把当前采样值写进这条记录的 `VAL` 字段。

## 参见

- [SWAT+ 模板](../templates/swatplus.md)
- [SWAT+ 流量抽取指南](swatplus-flow-extraction.md)
