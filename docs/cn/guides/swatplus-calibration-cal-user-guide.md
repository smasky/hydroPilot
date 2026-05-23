# SWAT+ `calibration.cal` 用户指南

这份文档只讲一件事：在 `version: swatplus` 下，你该怎么用 `calibration.cal` 这条新写入路径。

它是用户文档，不是内部设计说明。

## 先记住一件事

当你写：

```yaml
version: swatplus
```

现在 hydroPilot 会通过 `calibration.cal` 写入 SWAT+ 参数。

这意味着你不再需要：

- 手工准备参数所在的行列位置
- 在配置里直接指向 `parameters.bsn`、`hydrology.hyd` 这类源参数文件
- 预先在源工程目录里手工放一份 `calibration.cal`

这些工作现在都由模板来处理。

## 一个最常见的使用流程

大多数用户的使用流程可以概括成 5 步：

1. 把 `projectPath` 指到一个 SWAT+ 工程
2. 在 `parameters.design` 里声明要率定的参数
3. 如有需要，在 `parameters.physical` 里补充写入方式
4. 定义输出序列和目标函数
5. 按原来的方式运行 hydroPilot

如果只看用户心智，和旧路线相比，最大的变化只有一句话：

- 以前是“直接改源文件”
- 现在是“生成 SWAT+ 标定记录”

## 最小示例

```yaml
version: swatplus

basic:
  projectPath: ./Ames_sub1/TxtInOut
  workPath: ./work
  command: swatplus.exe

parameters:
  design:
    - name: surq_lag
      bounds: [0.05, 24.0]
    - name: esco
      bounds: [0.0, 1.0]

  physical:
    - name: surq_lag
      mode: v
    - name: esco
      mode: a

series:
  - id: flow
    sim:
      file: hydout_mon.txt
      variable: FLOW_OUT
      id: 1
      period: [2010, 2020]
    obs:
      file: obs_flow_monthly.txt
      rowRanges: [[1, 132]]
      colNum: 1

objectives:
  - name: nse
    series: flow
    metric: nse
    sense: max
```

## 怎么理解 `design` 和 `physical`

### `design`

`design` 是优化器看到的变量。

例如：

```yaml
design:
  - name: esco
    bounds: [0.0, 1.0]
```

它表达的是：

- 优化变量名叫 `esco`
- hydroPilot 会在 `[0.0, 1.0]` 这个范围内采样

### `physical`

`physical` 决定这个参数最终怎样写成 SWAT+ 的标定记录。

例如：

```yaml
physical:
  - name: esco
    mode: v
```

它表达的是：

- 这个参数会通过 `calibration.cal` 写入
- 它使用 `mode: v`
- 在 SWAT+ 里会对应 `CHG_TYPE = absval`

## `mode` 是怎么映射的

hydroPilot 的 `mode` 会映射到 SWAT+ 的 `CHG_TYPE`：

| `mode` | `CHG_TYPE` | 含义 |
|---|---|---|
| `v` | `absval` | 直接赋绝对值 |
| `a` | `abschg` | 做绝对增减 |
| `r` | `pctchg` | 做百分比变化 |

如果你之前已经熟悉 hydroPilot 里 SWAT 2012 的 `mode` 用法，那这一层用户感知其实还是连续的，变化只发生在最终写入目标上。

## 我需要自己创建 `calibration.cal` 吗

不需要。

hydroPilot 会在实例初始化阶段自动生成 instance 目录里的 `calibration.cal`。

所以源 SWAT+ 工程可以保持原样，即使一开始根本没有这份文件，也不影响这条主链路工作。

## 还需要关心源参数文件吗

通常不需要。

你依然是按 SWAT+ 参数名来选参数，但模板不再要求你从用户层面去关心：

- 这个参数原来在哪个文件里
- 对应哪一行
- 数值列从哪一列开始

这些知识现在收敛在模板和参数数据库内部。

## filter 还能不能写

可以继续写。

例如：

```yaml
physical:
  - name: esco
    mode: v
    filter:
      lu_mgt: cosy_lum
```

但当前阶段要明确边界：

- filter 语法还保留在 SWAT+ 模板里
- 它仍然属于这条迁移路线的一部分
- 但它还没有完全展开成最终的原生 `calibration.cal` 条件表达

所以从用户文档角度，它已经是公开写法；但从实现成熟度角度，这块还不是最终完成态。

## 目前已经比较稳定的部分

当前已经到位的点包括：

- SWAT+ 模板通过 `calibration.cal` 写参数
- 底层使用的是通用 `formatted_text` writer
- `calibration.cal` skeleton 自动生成
- 源工程不要求预先存在 `calibration.cal`
- SWAT+ 的 Tier 1 流量抽取路线已经有文档和配置方式

## 你现在还需要知道的边界

下面这些目前仍然算边界：

- 不是所有 SWAT+ 参数组都已经在 calibration 记录层面扩到同样深
- filter 到最终条件表达的展开还没有完全做完
- 仍然值得继续补更多真实工程的端到端验证

换句话说，这条路线现在已经是正式主线了，但一些更深的角落还在继续补齐。

## 推荐阅读顺序

如果你是第一次在 hydroPilot 里使用 SWAT+，建议按这个顺序看：

1. [SWAT+ 模板](../templates/swatplus.md)
2. [SWAT+ `calibration.cal` 写入链路](swatplus-calibration-cal.md)
3. [SWAT+ 流量抽取指南](swatplus-flow-extraction.md)

## 一句话总结

站在用户角度，最实用的理解就是：

- 继续写 `version: swatplus`
- 继续按模板方式声明参数
- 让 hydroPilot 自动生成和维护 `calibration.cal`
- 你更应该关注参数意义、`mode` 和率定目标，而不是底层文件位置
