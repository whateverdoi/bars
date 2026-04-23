# Bars

> 本项目使用 Rust 实现 [Advances in Financial Machine Learning](https://www.wiley.com/en-us/Advances+in+Financial+Machine+Learning-p-9781119482086) 中的各类 k线（Bars）

---

## 目录
- [使用示例](#使用示例)
- [标准k线](#标准k线)
- [信息驱动k线](#信息驱动k线)
- [为什么选择非时间k线](#为什么选择非时间k线)

---
## 使用示例

1m time bar示例
cargo run -- --input data/DOGEUSDT-aggTrades-2026-03.csv --output data/test_bars.csv --bar-type time1-m

Tick Imbalance Bar 示例：
cargo run -- --input data/DOGEUSDT-aggTrades-2026-03.csv --output data/test_tick_imbalance.csv --bar-type tick-imbalance

Dollar bar 示例：
cargo run -- --input data/DOGEUSDT-aggTrades-2026-03.csv --output data/test_dollar.csv --bar-type dollar

Volume Run Bar 示例：
cargo run -- --input data/DOGEUSDT-aggTrades-2026-03.csv --output data/test_volume_run.csv --bar-type volume-run

> **注意**：aggtrades为聚合逐笔成交，可以在[binance](https://data.binance.vision/)下载


## 标准k线

| # | 类型 | 采样方式 | 说明 |
|---|------|----------|------|
| 1 | Time Bars | 时间间隔 | 最常见，按固定时间间隔采样 |
| 2 | Tick Bars | 交易笔数 | 每 N 笔交易生成一个k线 |
| 3 | Volume Bars | 成交量 | 每 N 单位成交生成一个k线 |
| 4 | Dollar Bars | 美元价值 | 每 $N 价值生成一个k线 |

### 1. 时间k线 (Time Bars)

最常见也最容易获取的 k线，按固定时间间隔采样，如 1分钟、1小时、1天。

| 特点 | 说明 |
|------|------|
| 优点 | 简单易获取，数据来源广泛 |
| 缺点 | 不能根据市场活动调整采样频率，低交易量时段信息量少 |

**计算方法**：
```
bar_open_time = round_to_period(tick.timestamp)
tick_count = 0
volume_sum = 0
dollar_sum = 0

当 tick.timestamp - bar_open_time >= period 时:
    关闭当前 bar
    开始新 bar
```

### 2. Tick Bars

基于交易笔数采样，如每 10000 笔交易生成一个 k线。

| 特点 | 说明 |
|------|------|
| 优点 | 根据市场活动自动调整采样频率，交易活跃时 k线更密集 |
| 缺点 | 未考虑交易大小，单个大单和多笔小额交易产生相同数量的 k线 |

**计算方法**：
```
tick_count = 0

每收到一个 tick:
    tick_count += 1
    当 tick_count >= EBT (Expected Ticks Per Bar) 时:
        关闭当前 bar
        开始新 bar
        tick_count = 0
```

### 3. Volume Bars

基于成交量采样，如每 1000 单位成交生成一个 k线。

| 特点 | 说明 |
|------|------|
| 优点 | 解决了 Tick Bars 的局限性，考虑了每笔交易的交易量 |
| 缺点 | 价格大幅波动时，同样成交量可能产生不同美元价值 |

**计算方法**：
```
volume_sum = 0

每收到一个 tick:
    volume_sum += tick.volume
    当 volume_sum >= EVD (Expected Volume Per Dollar) 时:
        关闭当前 bar
        开始新 bar
        volume_sum = 0
```

### 5. Tick Imbalance Bars (TIB)

基于订单流不平衡度采样，捕捉买卖方向的不平衡信息。

**计算方法**：
```
第一步：定义 Tick Rule（根据价格变化确定买卖方向）
b_t = {
    b_{t-1}                if Δp_t = 0       // 价格不变时，继承前一个方向
    sign(Δp_t)            if Δp_t ≠ 0       // 价格上升为 +1（买），下降为 -1（卖）
}

第二步：累积有符号ticks
θ_T = Σ(t=1 to T) b_t  // 累积买卖方向

第三步：计算期望不平衡
E_0[T] = EMA(先前bars的T值)
P[b_t=1] = EMA(先前bars的买单比例)
E_0[θ_T] = E_0[T] × (2P[b_t=1] - 1)

第四步：采样条件
当 |θ_T| ≥ E_0[T] × |2P[b_t=1] - 1| 时：
    关闭当前 bar，开始新 bar
```

### 6. Volume Imbalance Bars (VIB)

基于成交量不平衡度采样。

**计算方法**：
```
θ_T = Σ(t=1 to T) b_t × v_t  // v_t 为成交量

E_0[θ_T] = E_0[T] × (2v^+ - E_0[v_t])
其中：
  v^+ = P[b_t=1] × E_0[v_t|b_t=1]  // 买单平均成交量
  v^- = P[b_t=-1] × E_0[v_t|b_t=-1]  // 卖单平均成交量

当 |θ_T| ≥ E_0[T] × |2v^+ - E_0[v_t]| 时：
    关闭当前 bar
```

### 7. Dollar Imbalance Bars (DIB)

基于美元价值不平衡度采样。

**计算方法**：
```
θ_T = Σ(t=1 to T) b_t × (p_t × v_t)  // 美元价值

期望值计算与 VIB 相同，只需将 v_t 替换为 p_t × v_t
```

### 8. Tick Run Bars (TRB)

基于连续同向交易检测。

**计算方法**：
```
θ_T = max {
    Σ(t|b_t=1) b_t,     // 买单tick总数
    Σ(t|b_t=-1) |b_t|   // 卖单tick总数
}

E_0[θ_T] = E_0[T] × max{P[b_t=1], 1-P[b_t=1]}

当 θ_T ≥ E_0[T] × max{P[b_t=1], 1-P[b_t=1]} 时：
    关闭当前 bar
```

### 9. Volume Run Bars (VRB)

基于连续同向成交量检测。

**计算方法**：
```
θ_T = max {
    Σ(t|b_t=1) b_t × v_t,      // 买单累积成交量
    Σ(t|b_t=-1) |b_t| × v_t    // 卖单累积成交量
}

E_0[θ_T] = E_0[T] × max {
    P[b_t=1] × E_0[v_t|b_t=1],
    (1-P[b_t=1]) × E_0[v_t|b_t=-1]
}

当 θ_T ≥ E_0[T] × max{...} 时：
    关闭当前 bar
```

### 10. Dollar Run Bars (DRB)

基于连续同向美元价值检测。

**计算方法**：
```
θ_T = max {
    Σ(t|b_t=1) b_t × (p_t × v_t),      // 买单累积美元价值
    Σ(t|b_t=-1) |b_t| × (p_t × v_t)    // 卖单累积美元价值
}

期望值计算与 VRB 相同，只需将 v_t 替换为 p_t × v_t
```

---

## 信息驱动k线

> 这类 k线 统称为 **Information-Driven Bars**，核心思想是根据市场信息决定何时生成 k线，而非固定时间间隔。

### Imbalance Bars

基于订单流不平衡度采样，捕捉买卖方向的不平衡信息。

| 子类型 | 采样基准 | 说明 |
|--------|----------|------|
| Tick Imbalance Bars (TIB) | 交易笔数 | 基于 tick imbalance 累积达到阈值 |
| Volume Imbalance Bars (VIB) | 成交量 | 基于 volume imbalance 累积达到阈值 |
| Dollar Imbalance Bars (DIB) | 美元价值 | 基于 dollar imbalance 累积达到阈值 |

**优点**：可以捕捉订单流中的信息不对称，在价格即将上涨或下跌前生成 k线。

#### 计算方法

##### 1. Tick Imbalance Bars (TIB)

**第一步**：定义 Tick Rule（根据价格变化确定买卖方向）
```
b_t = {
    b_{t-1}                if Δp_t = 0       // 价格不变时，继承前一个方向
    sign(Δp_t)            if Δp_t ≠ 0       // 价格上升为 +1（买），下降为 -1（卖）
}
```

**第二步**：累积有符号ticks
```
θ_T = Σ(t=1 to T) b_t  // 累积买卖方向
```

**第三步**：计算期望不平衡
```
E_0[T] = EMA(先前bars的T值)
P[b_t=1] = EMA(先前bars的买单比例)

E_0[θ_T] = E_0[T] × (2P[b_t=1] - 1)
```

**第四步**：采样条件
```
当 |θ_T| ≥ E_0[T] × |2P[b_t=1] - 1| 时：
    关闭当前 bar，开始新 bar
    重置 θ_T = 0
```

##### 2. Volume Imbalance Bars (VIB)

**计算方法**：类似 TIB，但将每个tick的成交量加权

```
θ_T = Σ(t=1 to T) b_t × v_t  // v_t 为第t笔交易的成交量

E_0[θ_T] = E_0[T] × (2v^+ - E_0[v_t])
其中：
  v^+ = P[b_t=1] × E_0[v_t|b_t=1]  // 买单平均成交量
  v^- = P[b_t=-1] × E_0[v_t|b_t=-1]  // 卖单平均成交量

当 |θ_T| ≥ E_0[T] × |2v^+ - E_0[v_t]| 时：
    关闭当前 bar
```

##### 3. Dollar Imbalance Bars (DIB)

**计算方法**：类似 VIB，但使用美元价值代替成交量

```
θ_T = Σ(t=1 to T) b_t × (p_t × v_t)  // 美元价值 = 价格 × 成交量

期望值计算与 VIB 相同，只需将 v_t 替换为 p_t × v_t
```

---

### Run Bars

基于连续同向交易检测，捕捉持续的趋势信息。

| 子类型 | 采样基准 | 说明 |
|--------|----------|------|
| Tick Run Bars (TRB) | 交易笔数 | 连续同向交易笔数达到阈值 |
| Volume Run Bars (VRB) | 成交量 | 连续同向成交量达到阈值 |
| Dollar Run Bars (DRB) | 美元价值 | 连续同向美元价值达到阈值 |

**优点**：可以检测持续的单边趋势，在趋势结束时生成 k线。

#### 计算方法

##### 1. Tick Run Bars (TRB)

**第一步**：计算当前运行长度（同一方向的tick计数）
```
θ_T = max {
    Σ(t|b_t=1) b_t,     // 买单tick总数
    Σ(t|b_t=-1) |b_t|   // 卖单tick总数
}
```

**第二步**：计算期望运行长度
```
E_0[T] = EMA(先前bars的T值)
P[b_t=1] = EMA(先前bars的买单比例)

E_0[θ_T] = E_0[T] × max{P[b_t=1], 1-P[b_t=1]}
```

**第三步**：采样条件
```
当 θ_T ≥ E_0[T] × max{P[b_t=1], 1-P[b_t=1]} 时：
    关闭当前 bar
```

**关键特性**：允许序列中断，计数而非抵消

##### 2. Volume Run Bars (VRB)

**计算方法**：计算同一方向的累积成交量

```
θ_T = max {
    Σ(t|b_t=1) b_t × v_t,      // 买单累积成交量
    Σ(t|b_t=-1) |b_t| × v_t    // 卖单累积成交量
}

E_0[θ_T] = E_0[T] × max {
    P[b_t=1] × E_0[v_t|b_t=1],
    (1-P[b_t=1]) × E_0[v_t|b_t=-1]
}

当 θ_T ≥ E_0[T] × max{...} 时：
    关闭当前 bar
```

##### 3. Dollar Run Bars (DRB)

**计算方法**：计算同一方向的累积美元价值

```
θ_T = max {
    Σ(t|b_t=1) b_t × (p_t × v_t),      // 买单累积美元价值
    Σ(t|b_t=-1) |b_t| × (p_t × v_t)    // 卖单累积美元价值
}

期望值计算与 VRB 相同，只需将 v_t 替换为 p_t × v_t
```

---

## 为什么选择非时间k线

传统的 Time Bars 假设收益率是独立同分布 (i.i.d.) 的，但实际研究发现：

| 假设 | 实际情况 |
|------|----------|
| 收益率服从正态分布 | 实际呈厚尾分布 |
| 收益率相互独立 | 存在显著自相关性 |
| 收益率时间平稳 | 具有时变性 |

### 研究表明

Dollar Bars 产生的序列更接近 i.i.d. 假设：

- ✅ 收益率更接近正态分布
- ✅ 自相关性更低（更独立）
- ✅ 时间稳定性更好
- ✅ 解决了 Volume Bars 在价格大幅波动时的问题

这对后续的特征工程、三重屏障标签（Triple-Barrier Labeling）和机器学习模型训练至关重要。

---

## 参考

- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley.