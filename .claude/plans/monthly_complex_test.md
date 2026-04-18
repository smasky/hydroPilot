# 月度复杂场景测试说明

## 背景

本测试基于 [scripts/test_monthly_complex.py](../../scripts/test_monthly_complex.py) 对应的月度 SWAT 复杂样例，目标是验证这次 dev_plan1 目标 1/2/3 的落地结果：

- 模板展开后的 general config 显式带 `writerType` / `readerType`
- runtime 读写实现通过 registry 分发
- SWAT 模板作为 discovery / library / builder / template 样板，能稳定导出带显式 I/O 类型的 `_general.yaml`

## 新增测试文件

- [tests/test_monthly_complex_io_protocol.py](../../tests/test_monthly_complex_io_protocol.py)

## 覆盖点

### 1. 模板展开协议验证

测试入口：`test_monthly_complex_template_expands_explicit_io_types`

验证内容：
- `examples/test_monthly_complex.yaml` 能被 `load_config()` 展开成 `version == "general"`
- design / physical / series / objectives / diagnostics 数量与脚本预期一致
- 所有 physical parameter 显式带 `writerType == "fixed_width"`
- 所有 series sim/obs extract 显式带 `readerType == "text"`
- 旁产物 `examples/test_monthly_complex_general.yaml` 已写出，并包含：
  - `writerType: fixed_width`
  - `readerType: text`

### 2. registry 分发验证

测试入口：`test_minimal_io_registries_dispatch_existing_implementations`

验证内容：
- `getWriter("fixed_width")` 返回 `FixedWidthWriter`
- `getReader("text")` 返回 `TextReader`
- 未注册类型会抛出 `ValueError`

## 依赖条件

该测试依赖本地 SWAT 工程目录：

- `E:\BMPs\TxtInOut`

如果该目录不存在，模板展开测试会自动 `skip`，因为 `load_config()` 在 SWAT template 模式下需要先做 discovery。

## 运行方式

在仓库根目录运行：

```bash
python -m pytest tests/test_monthly_complex_io_protocol.py -q
```

如果只想看详细输出：

```bash
python -m pytest tests/test_monthly_complex_io_protocol.py -vv
```

## 当前定位

这个测试主要验证“协议边界”和“模板展开结果”，不是完整 SWAT 数值回归测试。

也就是说，它解决的是：
- 配置里有没有显式 I/O 类型
- runtime 有没有按类型找实现
- SWAT 模板有没有把这些类型稳定写到 general config

而不是直接校验一次完整月度模拟的目标函数数值是否正确。
