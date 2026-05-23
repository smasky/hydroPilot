# SWAT+ 正式现状与用户指南

更新日期：2026-05-22

这份文档是当前仓库内 SWAT+ 支持的**正式汇总版**。

目标：

- 汇总 `.claude/` 下分散的 SWAT+ 草稿与结论
- 只保留**已被源码、真实项目、当前代码、当前测试共同支持**的事实
- 给出一份可直接面向使用者的说明

这份文档优先级高于以下历史草稿：

- `.claude/swatplus-current-status-2026-05-21.md`
- `.claude/swatplus-calibration-objects.md`
- `.claude/swatplus-filter-mapping.md`
- `.claude/swatplus-calibration-config-aligned.md`
- `.claude/swatplus-calibration-general-format.md`
- `.claude/swatplus-calibration-template.md`
- `.claude/swatplus-output-guide.md`

这些旧文件仍可作为过程记录，但如果与本文冲突，以本文为准。

---

## 1. 一句话结论

当前 `hydroPilot` 对 SWAT+ 的支持已经形成一条真实可用的主线：

- 模板入口：`version: swatplus`
- 模板展开：输出 `general` 配置
- 参数写入主线：`calibration.cal`
- writer：`formatted_text`
- 运行前初始化：支持自动生成 `calibration.cal`
- 输出提取：已支持一批 SWAT+ 文本输出

当前最准确的 support matrix 是：

| 组 | filter 支持 | 当前状态 |
|---|---|---|
| `bsn` | 无 | 已实现，按 global basin 处理，`OBJ_TOT=0` |
| `hru` | `object_id`, `lu_mgt`, `soil`, `hydro_name` | 已实现 |
| `sol` | `soil` | 已实现，**soil name -> HRU IDs** |
| `cha` | `object_id` | 已实现 |

当前仍未实现：

- 原生 `calibration.cal` `CONDS` 条件语法
- `HYD_GRP / TEXTURE / layer` 这类更细的 soil selector
- channel 的 `name/order` selector
- 更广对象空间的通用 targeting 抽象落地

---

## 2. 当前代码入口

### 2.1 模板入口

- [src/hydropilot/models/swatplus/template.py](/Users/smasky/Desktop/hydroPilot/hydroPilot/src/hydropilot/models/swatplus/template.py)

当前行为：

1. `SwatPlusTemplate.validate()` 已接入 SWAT+ 专属校验
2. `SwatPlusTemplate.build_config()` 会：
   - 读取项目元数据
   - 组装 series
   - 组装 parameters
   - 生成 `calibration.cal` skeleton
   - 输出 `general`

### 2.2 校验入口

- [src/hydropilot/models/swatplus/validate.py](/Users/smasky/Desktop/hydroPilot/hydroPilot/src/hydropilot/models/swatplus/validate.py)

当前会检查：

- `projectPath` 是否存在
- `file.cio / time.sim / print.prt / hru-data.hru` 是否存在
- 参数名是否在 SWAT+ 参数库中
- `filter` 是否用于允许的参数组
- `cha object_id` 是否满足基本规则
- series 的 `variable / file / row selection` 是否基本合法

### 2.3 参数展开入口

- [src/hydropilot/models/swatplus/builder.py](/Users/smasky/Desktop/hydroPilot/hydroPilot/src/hydropilot/models/swatplus/builder.py)

当前行为：

- 不 direct-write 原始项目文件
- 统一生成 `calibration.cal` 记录
- 在运行阶段只写 `VAL` 列
- `OBJ_TOT + object tail` 由模板层先算好

### 2.4 项目发现入口

- [src/hydropilot/models/swatplus/discovery.py](/Users/smasky/Desktop/hydroPilot/hydroPilot/src/hydropilot/models/swatplus/discovery.py)

当前已发现：

- `time.sim` / `print.prt`
- `hru-data.hru`
- `channel-lte.cha`
- 基础 HRU 元数据
- 基础 channel reach 数量
- soil/profile 解析基础能力已补齐作为支撑层

---

## 3. `calibration.cal` 路线现状

### 3.1 当前是正式主线

当前 SWAT+ 参数写入主线不是 direct-write，而是：

1. 参数展开为 `calibration.cal` 记录
2. 生成 skeleton
3. 运行前将 skeleton 初始化到实例目录
4. 每次 apply 时仅更新 `VAL`

### 3.2 当前已经做对的部分

- `mode -> CHG_TYPE`
  - `v -> absval`
  - `a -> abschg`
  - `r -> pctchg`
- 每个 physical parameter 对应 `calibration.cal` 一条记录
- `OBJ_TOT + tail` 可以用于 object targeting
- 没有源项目 `calibration.cal` 也能运行

### 3.3 当前还没做的部分

- `CONDS` 条件行
- layer 范围控制
- year/day window 控制
- 更复杂 selector 向 native calibration condition 的翻译

也就是说，当前是：

- `calibration.cal` 主线已经成立
- 但只使用了它的一个可用子集

---

## 4. `filter` 的正式语义

这是最关键的部分。

### 4.1 当前 `filter` 不是纯模型无关 selector

当前 `filter` 仍然是模板层语义，不是 general 层通用 targeting 抽象。

它现在的真实意义是：

- `models/swatplus` 用它决定如何生成 `OBJ_TOT + object tail`

### 4.2 当前按对象组的语义不同

#### `hydrology.hyd`

`filter` 解析为 HRU IDs。

允许的 key：

- `object_id`
- `lu_mgt`
- `soil`
- `hydro_name`

#### `soils.sol`

`filter` 入口是 **soil name**

但最终仍然解析为 **HRU IDs**。

这一点不是设计猜测，而是 SWAT+ FORTRAN 源码确认的结果：

- `cal_parmchg_read.f90`
  `case("sol") -> sp_ob%hru`
- `soil_data_module.f90`
  `Index:(layer,HRU)`

所以：

- soil/profile 名称用于识别“哪些 HRU 命中”
- `calibration.cal` 最终携带的对象 ID 仍是 HRU ID

#### `hyd-sed-lte.cha`

当前只支持：

- `object_id`

这里 `object_id` 对应 channel/reach 的顺序 ID。

#### `parameters.bsn`

不支持 `filter`。

`bsn` 当前按 global basin 处理：

- `OBJ_TOT=0`

### 4.3 当前不支持的 `filter`

当前仍不支持：

- `cal_group`
- `hsg`
- `texture`
- `plant`
- `pl_class`
- `res_typ`
- slope range
- soil layer selector
- channel `name/order` selector

如果用户写这些，当前不应被当成已支持能力。

---

## 5. Support Matrix

### 5.1 `bsn`

状态：

- 已实现
- global
- `OBJ_TOT=0`
- 无 `filter`

依据：

- `cal_parmchg_read.f90`
  `case("bsn") -> num_elem = 1`

对用户的含义：

- basin 参数可以调
- 但不是按对象筛一部分 basin
- 因为 basin 本来就是单对象语义

示例：

```yaml
parameters:
  design:
    - name: surq_lag
      bounds: [0.05, 24.0]
  physical:
    - name: surq_lag
      mode: v
```

当前不允许：

```yaml
physical:
  - name: surq_lag
    mode: v
    filter:
      lu_mgt: cosy_lum
```

### 5.2 `hru`

状态：

- 已实现
- 已在真实项目验证

支持 key：

- `object_id`
- `lu_mgt`
- `soil`
- `hydro_name`

典型参数：

- `esco`
- `epco`
- `perco`

示例：

```yaml
parameters:
  design:
    - name: esco
      bounds: [0.1, 0.9]
  physical:
    - name: esco
      mode: v
      filter:
        lu_mgt: cosy_lum
```

在真实 `Ames_sub1` 上，已验证：

- `OBJ_TOT=11`
- 命中 HRU IDs:
  - `1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12`

### 5.3 `sol`

状态：

- 已实现
- 但语义容易误解

当前正确表述是：

- 用户通过 `soil` 名称筛选
- 模板层通过 `hru-data.hru.soil` 找到命中 HRUs
- `calibration.cal` 最终写入 **HRU IDs**

不是：

- soil profile IDs

支持 key：

- `soil`

当前最保守匹配规则：

- exact match

也就是说：

- `soil_01` 只匹配 `soil_01`
- 不自动扩成 `soil_01-h1`

典型参数：

- `sol_bd`
- `awc`
- `k`

示例：

```yaml
parameters:
  design:
    - name: sol_bd
      bounds: [0.9, 2.5]
  physical:
    - name: sol_bd
      mode: v
      filter:
        soil: soil_01
```

当前语义：

- 命中所有 `hru-data.hru.soil == soil_01` 的 HRUs
- 写入这些 HRU IDs

注意：

- 这里 “soil 参数”
- 不等于 “object tail 写 soil profile index”

这件事已经被 SWAT+ FORTRAN 证实。

### 5.4 `cha`

状态：

- 已实现
- 最小支持

支持 key：

- `object_id`

不支持：

- `lu_mgt`
- `soil`
- `hydro_name`
- `name`
- `order`

典型参数：

- `ch_mann`
- `ch_erod`

示例：

```yaml
parameters:
  design:
    - name: ch_mann
      bounds: [0.01, 0.2]
  physical:
    - name: ch_mann
      mode: v
      filter:
        object_id: [2, 4]
```

当前语义：

- 直接将 `[2, 4]` 作为 channel/reach IDs
- 写入 `OBJ_TOT=2` 和对象尾部

Discovery 已支持：

- 从 `channel-lte.cha` 解析 `n_reaches`
- build 时做范围检查

---

## 6. 当前用户最应该知道的限制

### 6.1 `sol` 不是 profile-id targeting

很多人第一眼会以为：

- `soils.sol` 参数
- 应该写 soil profile ID

当前源码结论不是这样。

SWAT+ calibration 对 `sol` 的对象空间是：

- HRU

所以 `soil` 只是筛选入口，不是最终 object id 语义。

### 6.2 `sol` 当前只支持 exact match

例如：

- `soil_01`
- `soil_01-h1`

当前被视为不同值。

也就是说：

```yaml
filter:
  soil: soil_01
```

不会自动命中：

- `soil_01-h1`

这是当前最保守、最可控的实现。

### 6.3 `cha` 当前只支持 `object_id`

如果你写：

```yaml
filter:
  order: 3
```

当前不支持。

如果你写：

```yaml
filter:
  name: cha01
```

当前也不支持。

### 6.4 `bsn` 当前没有 filter

当前 basin 参数只能按全局对象处理。

---

## 7. 正式用户说明

下面是建议用户直接照着写的说明。

### 7.1 最小 SWAT+ 配置骨架

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

series:
  - id: flow
    sim:
      file: channel_yr.txt
      variable: flo_out
      id: 1
      period: [1977, 1980]
```

### 7.2 用户如何理解 `design` 和 `physical`

`design`：

- 优化器看到的参数
- 定义 bounds

`physical`：

- 最终写进 `calibration.cal` 的参数条目
- 可以指定 `mode`
- 可以指定 `filter`

### 7.3 `mode` 怎么写

当前：

- `v` = `absval`
- `a` = `abschg`
- `r` = `pctchg`

示例：

```yaml
physical:
  - name: esco
    mode: v
```

```yaml
physical:
  - name: cn2
    mode: a
```

```yaml
physical:
  - name: perco
    mode: r
```

### 7.4 `filter` 怎么写

#### HRU 参数

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
      object_id: [1, 3, 5]
```

```yaml
physical:
  - name: esco
    mode: v
    filter:
      soil: soil_02
```

#### Soil 参数

```yaml
physical:
  - name: sol_bd
    mode: v
    filter:
      soil: soil_01
```

这里要特别记住：

- 你写的是 soil name
- 但系统最后写入的是命中 HRUs 的 ID

#### Channel 参数

```yaml
physical:
  - name: ch_mann
    mode: v
    filter:
      object_id: [2, 4]
```

#### Basin 参数

不要写 `filter`：

```yaml
physical:
  - name: surq_lag
    mode: v
```

### 7.5 当前推荐写法和不推荐写法

推荐：

```yaml
physical:
  - name: esco
    mode: v
    filter:
      lu_mgt: cosy_lum
```

推荐：

```yaml
physical:
  - name: sol_bd
    mode: v
    filter:
      soil: soil_01
```

推荐：

```yaml
physical:
  - name: ch_mann
    mode: v
    filter:
      object_id: [2, 4]
```

不推荐：

```yaml
physical:
  - name: surq_lag
    mode: v
    filter:
      lu_mgt: cosy_lum
```

不推荐：

```yaml
physical:
  - name: ch_mann
    mode: v
    filter:
      soil: soil_01
```

不推荐：

```yaml
physical:
  - name: sol_bd
    mode: v
    filter:
      texture: SILT_LOAM
```

---

## 8. 典型案例

### 8.1 HRU 案例：按 landuse 调 `esco`

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

预期：

- 校验通过
- 展开后 `calibration.cal` 中 `OBJ_TOT > 0`
- 对象尾部是命中的 HRU IDs

### 8.2 Soil 案例：按 soil name 调 `sol_bd`

```yaml
version: swatplus
basic:
  projectPath: ./Ames_sub1
  workPath: ./work
  command: ./swatplus

parameters:
  design:
    - name: sol_bd
      bounds: [0.9, 2.5]
  physical:
    - name: sol_bd
      mode: v
      filter:
        soil: soil_01
series: []
```

预期：

- 校验通过
- 通过 `hru-data.hru.soil` 找到命中的 HRUs
- `calibration.cal` 尾部写入 HRU IDs

### 8.3 Channel 案例：按 reach IDs 调 `ch_mann`

```yaml
version: swatplus
basic:
  projectPath: ./Osu_1hru
  workPath: ./work
  command: ./swatplus

parameters:
  design:
    - name: ch_mann
      bounds: [0.01, 0.2]
  physical:
    - name: ch_mann
      mode: v
      filter:
        object_id: [2, 4]
series: []
```

预期：

- 校验通过
- `channel-lte.cha` 中 reach 数量已解析
- build 时做 object_id 范围检查
- `calibration.cal` 尾部写入 reach IDs `2, 4`

### 8.4 Basin 案例：全局调 `surq_lag`

```yaml
version: swatplus
basic:
  projectPath: ./Ames_sub1
  workPath: ./work
  command: ./swatplus

parameters:
  design:
    - name: surq_lag
      bounds: [0.05, 24.0]
  physical:
    - name: surq_lag
      mode: v
series: []
```

预期：

- 校验通过
- `OBJ_TOT=0`
- 作用于全局 basin 对象

---

## 9. 输出提取说明

当前 SWAT+ 输出组织方式与 SWAT2012 不一样。

SWAT+ 更接近：

```text
{object}_{report}_{frequency}.txt
```

例如：

- `basin_wb_aa.txt`
- `hru_wb_aa.txt`
- `channel_yr.txt`
- `channel_mon.txt`
- `hydout_day.txt`

当前已接入的一批重点 flow 类输出包括：

- `hydout_*`
- `hydin_*`
- `basin_wb_*`
- `channel_sd_*`

频率支持：

- `aa`
- `yr`
- `mo`
- `da`

以及兼容：

- `_mon`
- `_day`

### 9.1 当前最接近 SWAT2012 `output.rch` 的路线

如果你的思路是：

- “像 SWAT2012 一样提某个 reach 的流量”

当前在 SWAT+ 下最接近的是：

- `channel_*`
- 变量如 `flo_out`

示例：

```yaml
series:
  - id: flow
    sim:
      file: channel_yr.txt
      variable: flo_out
      id: 1
      period: [1977, 1980]
```

---

## 10. 真实验证情况

当前已完成的验证包括：

- SWAT+ 源码本机编译成功
- 真实 `Ames_sub1` 运行成功
- hydroPilot 对 `Ames_sub1` 做过 smoke test
- `hydrology.hyd` filter 在真实项目上验证通过
- `parameters.bsn` 的 global 语义被源码确认
- `soils.sol` 的 HRU-ID 语义被 FORTRAN 源码确认
- `hyd-sed-lte.cha` 的 `object_id` 路线已通过 discovery + tests 验证

自动化测试收口时状态：

- `167 passed`

---

## 11. 仍然没有做的东西

下面这些不要误认为已经支持：

- `calibration.cal` native `CONDS`
- `cal_group / hsg / texture / plant / pl_class / res_typ`
- soil layer selector
- soil hydro-suffix 自动扩展匹配
- cha `name` selector
- cha `order` selector
- 通用 targeting 抽象真正落到 general 层

---

## 12. 对使用者的最终建议

如果你现在要实际用 SWAT+，建议这样理解：

1. `calibration.cal` 路线已经是正式主线
2. 先优先使用已经明确支持的最小集合
3. 对 `sol` 要记住：
   - 入口是 soil name
   - 最终对象 ID 是 HRU IDs
4. 对 `cha` 要记住：
   - 现在只开 `object_id`
5. 对 `bsn` 要记住：
   - 不要写 `filter`

最稳的当前支持矩阵就是：

| 参数组 | 推荐 filter |
|---|---|
| `hydrology.hyd` | `object_id / lu_mgt / soil / hydro_name` |
| `soils.sol` | `soil` |
| `hyd-sed-lte.cha` | `object_id` |
| `parameters.bsn` | 不写 |

---

## 13. 简短总结

如果要一句话概括当前 SWAT+ 支持现状：

> SWAT+ 的 `calibration.cal` 主线路线已经正式成立，`bsn / hru / sol / cha` 四类最小支持边界已经明确，其中 `sol` 的关键点是“用 soil name 识别目标，但 calibration object space 仍是 HRU IDs”。

