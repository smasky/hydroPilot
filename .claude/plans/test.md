# 测试

基于SWAT项目进行测试


# 场景一

项目地址: E:\\BMPs\\TxtInOut
类型：月模拟

## 测试一

测试series在不同时间能够正常读取
series:
  - id: flow
    desc: "Monthly streamflow at outlet"
    sim:
      file: output.rch
      subbasin: 62
      period: [2019-02, 2021-11] #非整年  或者是[2019-02-03, 2021-11-01] 情况下，也应该和[2019-02, 2021-11]一致
      timestep: monthly
      colSpan: [50, 61]
    obs:
      file: obs_flow_monthly.txt
      rowRanges:
        - [1, 36]
      colSpan: [1, 12]


## 测试二

series衍生，比如基于id为flow的series，乘以2，或者进行量纲转化，需要call外部函数

