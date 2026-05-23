# SWAT+ 当前支持现状

更新日期：2026-05-21

这份文档只描述**当前真实代码状态**，不描述目标状态，也不提前承诺尚未实现的能力。

---

## 1. 一句话结论

目前 `hydroPilot` 对 SWAT+ 的支持，已经具备一条可运行的主线：

- 模板入口：`version: swatplus`
- 模板输出：展开为 `version: general`
- 参数写入主线：通过 `calibration.cal`
- writer：`formatted_text`
- 运行前初始化：支持在实例目录中生成 `calibration.cal`
- 序列提取：已覆盖一批 SWAT+ 文本输出

但是，**对象定向（targeting / filter）这一块目前只完成了 HRU 一条支路**，还没有形成广义、通用、按官方对象空间完整展开的方案。

所以现状不是：

- “SWAT+ 所有参数组都已经支持 filter”

而是：

- `hydrology.hyd` 中的 HRU 参数：当前支持 `filter`
- `parameters.bsn`：当前不支持 `filter`，会在校验阶段拒绝
- `soils.sol`：当前不支持 `filter`，会在校验阶段拒绝
- `hyd-sed-lte.cha`：按当前代码逻辑，也不支持 `filter`

---

## 2. 当前已经打通的主链路

### 2.1 模板链路

当前 SWAT+ 模板入口在：

- [src/hydropilot/models/swatplus/template.py](/Users/smasky/Desktop/hydroPilot/hydroPilot/src/hydropilot/models/swatplus/template.py)

当前行为：

1. `SwatPlusTemplate.validate()` 已接入 `validate_swatplus_config()`
2. `SwatPlusTemplate.build_config()` 会：
   - 读取项目元数据
   - 组装 `series`
   - 组装 `parameters`
   - 生成 `calibration.cal` skeleton
   - 输出 `general` 配置

所以现在 `prepare_config()` / `load_config()` 的真实主链路里，SWAT+ 模板校验已经生效，不再只是独立函数可用。

### 2.2 参数写入链路

当前 SWAT+ 参数不是 direct-write 到原始项目文件，而是：

- 先把参数条目转换成 `calibration.cal` 的记录
- 再通过 `formatted_text` 只写每条记录中的 `VAL` 列

当前 builder 在：

- [src/hydropilot/models/swatplus/builder.py](/Users/smasky/Desktop/hydroPilot/hydroPilot/src/hydropilot/models/swatplus/builder.py)

当前关键事实：

- `calibration.cal` header 和 skeleton 会自动生成
- 即使原项目没有 `calibration.cal`，实例初始化阶段也可以创建
- 每个 resolved physical parameter 对应 `calibration.cal` 中一条记录

### 2.3 校验链路

当前 SWAT+ 专属校验在：

- [src/hydropilot/models/swatplus/validate.py](/Users/smasky/Desktop/hydroPilot/hydroPilot/src/hydropilot/models/swatplus/validate.py)

当前会检查：

- `projectPath` 是否存在
- `file.cio / time.sim / print.prt / hru-data.hru` 是否存在
- 参数名是否在 SWAT+ 参数库中
- `filter` 是否用于允许的参数组
- `series.sim.variable` / 文件 / 行选择是否基本合法

---

## 3. 当前 `filter` 的真实语义

这是目前最容易让人误解的地方。

### 3.1 当前 `filter` 不是“SWAT+ 全对象空间通用 targeting”

当前 `filter` 的实现依赖：

- `hru-data.hru`
- HRU 元数据字段：
  - `lu_mgt`
  - `soil`
  - `hydro_name`
  - 以及直接给 `object_id`

当前真实流程是：

1. 读取 `hru-data.hru`
2. 用 `filter` 筛选 HRU 元数据
3. 得到一组 HRU IDs
4. 把这些 ID 写到 `calibration.cal` 记录的 `OBJ_TOT + object tail`

所以当前它本质上是：

- **HRU-scoped object targeting MVP**

不是：

- basin / soil / channel / aquifer / reservoir 等对象空间的通用 targeting

### 3.2 当前允许的 `filter` 键

当前允许的键来自 `FILTERABLE_HRU_FIELDS`：

- `lu_mgt`
- `soil`
- `hydro_name`
- 以及 builder 里额外支持的 `object_id`

当前逻辑：

- 同一个字段内的 list：OR
- 多个字段同时出现：AND

示例：

```yaml
physical:
  - name: esco
    mode: v
    filter:
      lu_mgt: cosy_lum
```

```yaml
physical:
  - name: esco
    mode: v
    filter:
      lu_mgt: [cosy_lum, mntill_corn_lum]
      soil: soil_02
```

上面第二种写法表示：

- `lu_mgt` 在两个值里任选其一
- 同时 `soil` 必须等于 `soil_02`

### 3.3 当前不支持的 `filter` 语义

当前不支持：

- 原生 `calibration.cal` condition 语法
  - 例如 `cal_group`
  - `hsg`
  - texture 类条件
- 范围条件
  - 例如 slope range
- 非 HRU 对象空间的 filter 解析
  - basin
  - soil/profile
  - channel
  - aquifer
  - reservoir

也就是说，当前 `filter` 还不是一个“通用 selector 体系”，只是 HRU 这条支路先落了。

---

## 4. 当前按参数组划分的支持状态

### 4.1 `hydrology.hyd`

状态：

- **支持 `filter`**
- **真实项目已验证 accepted+active**

原因：

- 这一组参数当前被视为 HRU-scoped
- `filter` 可以稳定解析成 HRU IDs

典型参数：

- `esco`
- `epco`
- `perco`

当前允许写法示例：

```yaml
version: swatplus
basic:
  projectPath: ./Ames_sub1
  workPath: ./work
  command: ./swatplus
parameters:
  design:
    - name: esco
      bounds: [0.1, 0.9]
  physical:
    - name: esco
      mode: v
      filter:
        lu_mgt: cosy_lum
series: []
```

在真实 `Ames_sub1` 上，当前已经验证出：

- `OBJ_TOT=11`
- object tail IDs:
  - `1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12`

也就是：

- `Ames_sub1` 里所有 `lu_mgt=cosy_lum` 的 HRUs 都被命中
- HRU 2 被正确排除

这说明：

- 当前 HRU targeting 不是假支持
- 它已经在真实项目上落成了有效 `calibration.cal` 记录

### 4.2 `parameters.bsn`

状态：

- **不支持 `filter`**
- **当前会在验证阶段直接拒绝**

原因不是官方禁止，而是：

- 当前实现出来的 `filter` 只会解析成 HRU IDs
- `parameters.bsn` 是 basin-level 参数，不应接受 HRU object tail

典型参数：

- `surq_lag`
- `evap_adj`
- `scoef`

当前会报错的示例：

```yaml
parameters:
  design:
    - name: surq_lag
  physical:
    - name: surq_lag
      mode: v
      filter:
        lu_mgt: cosy_lum
```

当前主链路下的预期报错：

```text
filter is only supported for per-HRU parameters (source file hydrology.hyd).
'surq_lag' originates from 'parameters.bsn' and does not support per-object filtering.
```

所以当前 `bsn` 的真实状态是：

- 参数本身支持通过 `calibration.cal` 调整
- 但不支持借用当前这套 HRU `filter`

### 4.3 `soils.sol`

状态：

- **不支持 `filter`**
- **当前会在验证阶段直接拒绝**
- **即使绕过验证，builder 也不会为它写入 object tail**

原因：

- `soils.sol` 对应的是 soil/profile / layer 这套对象空间
- 当前没有建立 soil metadata / soil object id 映射
- 所以不能把 HRU IDs 假装当成 soil IDs

典型参数：

- `sol_bd`
- `awc`
- `k`

当前会报错的示例：

```yaml
parameters:
  design:
    - name: sol_bd
  physical:
    - name: sol_bd
      mode: v
      filter:
        soil: soil_02
```

当前结论：

- 校验层拒绝
- builder 防御层也成立
- 即使强行绕过验证，`OBJ_TOT` 仍会保持 `0`

所以这组不是“已经半支持”，而是：

- 参数库已有条目
- 但 targeting/filtering 语义没有接出来

### 4.4 `hyd-sed-lte.cha`

状态：

- **按当前代码逻辑，也不支持 `filter`**
- **当前应被验证层拒绝**

原因：

- 当前 `_FILTERABLE_SOURCE_FILES` 只有 `hydrology.hyd`
- channel/reach 对象空间还没有接到 `filter -> object IDs` 这条链路上

典型参数：

- `wd`
- `dp`
- `slp`
- `len`

注意：

- 这不代表 channel 参数不能通过 `calibration.cal` 调整
- 只代表当前这套 `filter` 还不能用来对 channel 对象做定向

---

## 5. 当前 `calibration.cal` 路线的真实能力

### 5.1 已实现的部分

当前已实现：

- 自动生成 `calibration.cal`
- 自动生成 skeleton
- 每个 physical param 一条记录
- `mode -> CHG_TYPE`
  - `v -> absval`
  - `a -> abschg`
  - `r -> pctchg`
- 通过 `formatted_text` 写 `VAL` 列
- HRU 参数上可写 `OBJ_TOT + HRU IDs`

示意 skeleton：

```text
Number of parameters:
1

NAME        CHG_TYPE             VAL    CONDS    LYR1    LYR2   YEAR1   YEAR2    DAY1    DAY2OBJ_TOT
esco         absval                  0.000000        0       0       0       0        0       0       0      11       1       3       4       5       6       7       8       9      10      11      12
```

### 5.2 尚未实现的部分

当前未实现：

- 原生 `CONDS` 条件语法
- 条件附加行
- layer-specific targeting
- year/day window targeting
- 非 HRU 对象空间的 object-id targeting

也就是说，当前 `calibration.cal` 路线虽然已经是主线，但还只是其中一个可用子集，不是全量 SWAT+ calibration language。

---

## 6. 当前 series 支持现状

这部分相对比参数 targeting 更完整一些。

当前已经确认：

- SWAT+ 文本输出系列已接入
- Tier 1 flow 系列已覆盖到 `aa / yr / mo / da`
- 当前是通过数据库映射 `file + variable -> colNum/colSpan`

当前已知已经补齐的一批 flow 类源包括：

- `hydout_*`
- `hydin_*`
- `basin_wb_*`
- `channel_sd_*`

其中 frequency 命名兼容：

- `_aa`
- `_yr`
- `_mon`
- `_day`

以及兼容旧检测逻辑里提到的：

- `_mo`
- `_da`

这部分总体上比 parameter targeting 更稳定，当前混乱主要不在这里。

---

## 7. 真实测试和验证现状

### 7.1 已完成的真实项目验证

当前已完成：

- 真实 SWAT+ 源码编译成功
- 真实 `Ames_sub1` 运行成功
- hydroPilot 对 `Ames_sub1` 做过 smoke test
- 当前 HRU filter 在 `Ames_sub1` 上已实测为 active

### 7.2 当前自动化测试状态

本轮收口时，coordinator 报告为：

- `152 tests pass`

已覆盖的关键点包括：

- SWAT+ template validate 接线
- `prepare_config` 主链路下的 basin filter 拒绝
- `prepare_config` 主链路下的 HRU filter 通过
- builder scope gate
- skeleton row count / mode consistency

---

## 8. 当前最混乱、最容易误解的点

这是我建议你重点看的部分。

### 8.1 “SWAT+ 支持 calibration.cal” 不等于 “SWAT+ 所有对象空间 targeting 都支持了”

当前已经支持的是：

- `calibration.cal` 主线

当前没有完整支持的是：

- SWAT+ 官方 calibration object space 的全量 targeting

### 8.2 “参数已入库” 不等于 “该参数组已经支持 filter”

例如：

- `sol_bd` 已在参数库里
- 但 `sol_bd + filter` 当前不支持

也就是说：

- 参数位置数据库
- 参数可被 calibration.cal 调整
- 参数支持对象定向筛选

这是三件不同的事，当前不能混为一谈。

### 8.3 当前 `filter` 名字容易让人误以为是通用 targeting

事实上当前它只是：

- HRU metadata selector

而不是：

- 通用 object selector

如果后面要做广义方案，这一层抽象需要重构。

---

## 9. 当前可以怎么用

### 9.1 当前推荐用法

如果你现在要稳定使用 SWAT+，建议这样理解：

- 把 SWAT+ 主线路线当成可用
- 把 `hydrology.hyd` 的 HRU 参数 filter 当成已落地能力
- 把 `bsn/sol/cha` 参数上的 `filter` 视为当前未开放

一个当前推荐的最小案例：

```yaml
version: swatplus
basic:
  projectPath: ./Ames_sub1
  workPath: ./work
  command: ./swatplus

parameters:
  design:
    - name: esco
      bounds: [0.1, 0.9]
  physical:
    - name: esco
      mode: v
      filter:
        lu_mgt: cosy_lum

series:
  - id: flow
    sim:
      file: channel_sd_aa.txt
      variable: flo_out
      id: 1
      period: [1977, 1980]
```

### 9.2 当前不推荐写法

当前不推荐，也不会通过的写法：

```yaml
physical:
  - name: surq_lag
    mode: v
    filter:
      lu_mgt: cosy_lum
```

```yaml
physical:
  - name: sol_bd
    mode: v
    filter:
      soil: some_soil
```

```yaml
physical:
  - name: wd
    mode: v
    filter:
      object_id: [1, 2, 3]
```

最后这个 `wd` 的例子尤其要注意：

- 即使 `object_id` 看起来“像是更通用的指定对象”
- 当前校验层仍会因为 `wd` 不属于 `hydrology.hyd` 而拒绝

---

## 10. 下一步如果要做“范围更广”的支持，真正缺什么

如果后面要按你的要求，把能接上的尽量都接上，那真正缺的不是多写几个 if，而是下面这些基础能力：

### 10.1 通用 targeting 抽象

当前缺：

- object space
- selector spec
- selector resolution
- resolved object ids

这几层的通用抽象

### 10.2 SWAT+ 对象空间映射

至少要分别回答：

- `bsn` 怎么表达 targeting，是否本来就是全局单对象
- `sol` 的对象 id 从哪里来
- `cha` 的对象 id 从哪里来
- 是否还有 `aqu` / `res` 等后续对象空间值得接

### 10.3 元数据发现能力

当前只有：

- `hru-data.hru -> HRU metadata`

后面如果扩到更广，需要至少补：

- soil/profile metadata
- channel/reach metadata
- 可能的 aquifer / reservoir metadata

### 10.4 模板层统一写法

现在的 `filter` 已经带有强 HRU 色彩。

如果要做范围更广的支持，后面要么：

- 继续叫 `filter`，但重构成按对象空间分流的 selector

要么：

- 设计一个更通用、更明确的 targeting 字段

这个需要单独定方案，不能在当前混合状态下继续外推。

---

## 11. 当前最准确的状态表

| 项目 | 当前状态 | 备注 |
|---|---|---|
| SWAT+ 模板入口 | 已接通 | `version: swatplus` |
| 模板校验接线 | 已接通 | `SwatPlusTemplate.validate()` 已生效 |
| `calibration.cal` 主线 | 已接通 | `formatted_text` |
| 自动生成 `calibration.cal` | 已接通 | skeleton + init |
| `hydrology.hyd` 参数 | 可用 | HRU filter 已实测 |
| `parameters.bsn` 参数 | 可用但不支持 filter | filter 会拒绝 |
| `soils.sol` 参数 | 可用但不支持 filter | filter 会拒绝 |
| `hyd-sed-lte.cha` 参数 | 已入库部分参数，但 filter 未开放 | 当前应拒绝 |
| 原生 `CONDS` 语法 | 未实现 | 还没接 |
| layer / year / day targeting | 未实现 | 还没接 |
| 通用对象空间 targeting | 未实现 | 当前只有 HRU MVP |

---

## 12. 总结

如果要一句话概括当前 SWAT+ 支持现状：

> SWAT+ 的 `calibration.cal` 主线路线已经成立，HRU 参数的 object targeting 已经真实可用，但整个 targeting 体系还停留在 HRU MVP 阶段，没有扩展成覆盖 basin / soil / channel 等对象空间的通用方案。

这也是为什么你会觉得它现在“支持得有点混乱”：

- 主链路是真的
- HRU targeting 也是真的
- 但对象空间抽象还没有完全展开
- 所以会出现“参数能调，但 filter 不能用”的不对称状态

