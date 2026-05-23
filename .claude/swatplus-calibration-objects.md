# SWAT+ `calibration.cal` 对象编号语义说明

这份文档只回答一个问题：

- `OBJ_TOT` 是什么
- 后面跟着的对象编号到底表示什么
- 它和 `HRUID`、`SUBID` 的关系该怎么理解

---

## 1. 先说结论

`OBJ_TOT` 不是对象类型，也不是对象 ID 本身。

它表示：

- 这条参数修改记录后面显式给了多少个对象编号

而这些对象编号到底代表什么，要看该参数在 SWAT+ 参数定义里的 `ob_typ`。

也就是说，不能一概理解成：

- HRU 参数 -> 一定是 `HRUID`
- subbasin 参数 -> 一定是 `SUBID`

更准确的理解是：

- **对象编号的编号空间由 `ob_typ` 决定**

---

## 2. 源码依据

### 2.1 参数定义里有对象类型 `ob_typ`

在 `calibration_data_module.f90` 中，参数定义包含：

- `ob_typ`

注释含义是：

- parameter is associated with object type (hru, chan, res, basin)

也就是说，参数天然绑定在某一类对象空间上。

### 2.2 参数修改记录里读取对象数量

在 `cal_parmchg_read.f90` 中，主记录最后会读到：

- `nspu`

如果 `nspu > 0`，后续就继续读取对象编号列表。

所以：

- `OBJ_TOT` 可以看作外部工具层面对 `nspu` 的展示名
- 它本质上表示对象编号数量

### 2.3 源码按 `ob_typ` 分流对象空间

在 `cal_parmchg_read.f90` 中，SWAT+ 按 `ob_typ` 判断这条参数修改应该作用在哪一类对象上。

支持的对象类型至少包括：

- `hru`
- `rdt`
- `plt`
- `lyr`
- `sol`
- `hlt`
- `ru`
- `aqu`
- `cha`
- `swq`
- `res`
- `sdc`
- `rte`
- `bsn`
- `pcp`
- `tmp`
- `gwf`
- `gwf_riv`
- `gwf_sgl`

---

## 3. `OBJ_TOT` 应该怎么理解

假设一条记录里：

```text
OBJ_TOT = 3
```

它的意思不是：

- 对象类型是 3

也不是：

- 作用于对象 ID 3

而是：

- 后面会跟 3 个对象编号

例如：

```text
... OBJ_TOT = 3   1  5  9
```

表示：

- 这条修改规则显式作用于 3 个对象
- 它们的编号分别是 `1, 5, 9`

但这 3 个编号究竟表示什么对象，要由 `ob_typ` 决定。

---

## 4. 典型对象类型的理解方式

下面这些是当前比较稳的理解。

### 4.1 `hru`

如果参数的 `ob_typ = hru`：

- 后面的对象编号可以理解为 HRU 对象编号

这时你的直觉基本成立：

- `OBJ_TOT` 后面的数字，近似可以理解成 HRU IDs

### 4.2 `bsn`

如果参数的 `ob_typ = bsn`：

- 这不是 `SUBID` 心智
- 而是 basin 单一对象

源码里对 `bsn` 的处理是：

- `num_elem = 1`

也就是说：

- basin 参数本质上作用于一个全局 basin 对象
- 不是按 subbasin 编号空间来理解

所以这里不应理解为：

- subbasin 参数 -> `SUBID`

### 4.3 `cha`

如果参数的 `ob_typ = cha`：

- 后面的对象编号更接近 channel 对象编号

### 4.4 `aqu`

如果参数的 `ob_typ = aqu`：

- 后面的对象编号更接近 aquifer 对象编号

### 4.5 `sol` / `lyr`

如果参数作用在土壤或分层对象：

- 对象编号就不再是简单的 HRU/子流域心智
- 还要结合层范围字段一起看

---

## 5. 回到你最关心的两个问题

### 5.1 如果是 HRU 参数，是不是 `HRUID`

可以近似这样理解：

- **是，通常就是 HRU 对象编号空间**

但更严谨的话，应该说：

- 是 `ob_typ = hru` 对应的对象编号

### 5.2 如果是 subbasin 参数，是不是 `SUBID`

**不是一个稳定成立的理解。**

SWAT+ calibration 这里更常见的是：

- `bsn` 表示 basin 全局对象
- 而不是 `subbasin` 对象空间

所以不能简单套用：

- subbasin 参数 -> `SUBID`

---

## 6. 对 hydroPilot 设计的直接启发

这件事说明一个很关键的点：

- `OBJ_TOT + object ids`

不能在通用层被理解成：

- `hruIds`
- `subIds`
- `channelIds`

更稳的内部抽象应该是：

- `objectType`
- `objectIds`

由 `models/swatplus` 决定：

- 这个参数属于哪类对象
- 这些编号在哪个对象空间里解释

而不是把解释逻辑塞进通用 writer。

---

## 7. 当前最稳的表达方式

如果以后要在 hydroPilot 内部描述一条 calibration 参数修改，建议先按下面这个心智理解：

```yaml
parameter: esco
objectType: hru
objectIds: [1, 3, 5]
```

或者：

```yaml
parameter: surlag
objectType: bsn
objectIds: []
```

这里：

- `objectIds: []`
  - 表示不显式列对象
  - 由参数本身作用于对应对象空间

---

## 8. 当前仍需继续核实的点

虽然上述理解已经比“HRUID / SUBID 二选一”稳很多，但仍有一些点后续需要继续核实：

- 每种 `ob_typ` 的对象编号具体来自哪张对象表
- `rdt / hlt / sdc / rte / gwf_*` 这些类型在实际文件中的编号空间含义
- `OBJ_TOT = 0` 时 SWAT+ 默认如何解释对象作用域
- 条件记录和对象编号之间的优先关系

所以这份文档当前最适合用来：

- 帮助统一对象编号心智
- 避免把 `OBJ_TOT` 误解成 `SUBID`
- 为后续配置层字段命名提供依据
