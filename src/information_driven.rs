// src/information_driven.rs
// 信息驱动的Bars实现

use crate::types::{Tick, Bar, Direction, EWMACalculator};
use chrono::{DateTime, Utc};

/// 信息驱动Bar的类型
#[derive(Debug, Clone, Copy)]
pub enum InformationDrivenBarType {
    /// Tick Imbalance Bars - 基于tick数的不平衡
    TickImbalance,
    /// Volume Imbalance Bars - 基于成交量的不平衡
    VolumeImbalance,
    /// Dollar Imbalance Bars - 基于美元价值的不平衡
    DollarImbalance,
    /// Tick Run Bars - 基于tick数的运行
    TickRun,
    /// Volume Run Bars - 基于成交量的运行
    VolumeRun,
    /// Dollar Run Bars - 基于美元价值的运行
    DollarRun,
}

/// Tick Rule计算器 - 根据价格变化确定买卖方向
#[derive(Debug, Clone)]
pub struct TickRuleCalculator {
    last_direction: Option<Direction>,
    last_price: f64,
}

impl TickRuleCalculator {
    pub fn new() -> Self {
        Self {
            last_direction: None,
            last_price: 0.0,
        }
    }

    /// 根据tick rule计算tick的方向
    pub fn calculate_direction(&mut self, tick: &Tick) -> Direction {
        let price_change = tick.price - self.last_price;
        
        let direction = if price_change > 0.0 {
            Direction::Buy
        } else if price_change < 0.0 {
            Direction::Sell
        } else {
            // 价格不变时，继承前一个方向
            self.last_direction.unwrap_or(Direction::Buy)
        };

        self.last_direction = Some(direction);
        self.last_price = tick.price;
        
        direction
    }

    /// 重置计算器
    pub fn reset(&mut self) {
        self.last_direction = None;
        self.last_price = 0.0;
    }
}

/// Imbalance Bar 聚合器
#[derive(Debug)]
pub struct ImbalanceBarAggregator {
    bar_type: InformationDrivenBarType,
    tick_rule: TickRuleCalculator,
    
    // 当前bar的状态
    current_bar: Option<Bar>,
    bar_start_time: Option<DateTime<Utc>>,
    
    // 累积值
    theta: f64,  // 当前不平衡/运行值
    volume_by_direction: (f64, f64),  // (buy_volume, sell_volume)
    dollar_by_direction: (f64, f64),  // (buy_dollar, sell_dollar)
    tick_count_by_direction: (u64, u64),  // (buy_count, sell_count)
    
    // 参数估计器（使用EWMA）
    alpha: f64,  // EWMA平滑系数
    expected_bar_length: EWMACalculator,  // E_0[T]
    buy_probability: EWMACalculator,  // P[b_t=1]
    buy_volume_expectation: EWMACalculator,  // E_0[v_t|b_t=1]
    sell_volume_expectation: EWMACalculator,  // E_0[v_t|b_t=-1]
    buy_dollar_expectation: EWMACalculator,
    sell_dollar_expectation: EWMACalculator,
}

impl ImbalanceBarAggregator {
    pub fn new(bar_type: InformationDrivenBarType, alpha: f64) -> Self {
        let mut aggregator = Self {
            bar_type,
            tick_rule: TickRuleCalculator::new(),
            
            current_bar: None,
            bar_start_time: None,
            
            theta: 0.0,
            volume_by_direction: (0.0, 0.0),
            dollar_by_direction: (0.0, 0.0),
            tick_count_by_direction: (0, 0),
            
            alpha,
            expected_bar_length: EWMACalculator::new(alpha),
            buy_probability: EWMACalculator::new(alpha),
            buy_volume_expectation: EWMACalculator::new(alpha),
            sell_volume_expectation: EWMACalculator::new(alpha),
            buy_dollar_expectation: EWMACalculator::new(alpha),
            sell_dollar_expectation: EWMACalculator::new(alpha),
        };
        
        // 初始化默认值 - 使用合理的初始期望值
        aggregator.expected_bar_length.update(100.0);  // 初始期望100个ticks
        aggregator.buy_probability.update(0.5);  // 初始50%概率
        aggregator.buy_volume_expectation.update(1000.0);
        aggregator.sell_volume_expectation.update(1000.0);
        aggregator.buy_dollar_expectation.update(100.0);
        aggregator.sell_dollar_expectation.update(100.0);
        
        aggregator
    }

    pub fn add_tick(&mut self, mut tick: Tick) -> Option<Bar> {
        // 计算tick的方向
        let direction = self.tick_rule.calculate_direction(&tick);
        tick.direction = Some(direction);
        
        // 初始化bar
        if self.current_bar.is_none() {
            self.start_new_bar(&tick);
        }

        // 更新bar
        self.update_current_bar(&tick, direction);

        // 检查是否应该关闭bar
        if self.should_close_bar() {
            let closed_bar = self.close_current_bar();
            self.start_new_bar(&tick);
            closed_bar
        } else {
            None
        }
    }

    fn start_new_bar(&mut self, tick: &Tick) {
        self.bar_start_time = Some(tick.timestamp);
        self.theta = 0.0;
        self.volume_by_direction = (0.0, 0.0);
        self.dollar_by_direction = (0.0, 0.0);
        self.tick_count_by_direction = (0, 0);
        
        self.current_bar = Some(Bar {
            open: tick.price,
            high: tick.price,
            low: tick.price,
            close: tick.price,
            volume: tick.volume,
            timestamp: tick.timestamp,
        });
    }

    fn update_current_bar(&mut self, tick: &Tick, direction: Direction) {
        let volume = tick.volume as f64;
        let dollar = tick.price * volume;

        // 更新方向统计
        match direction {
            Direction::Buy => {
                self.volume_by_direction.0 += volume;
                self.dollar_by_direction.0 += dollar;
                self.tick_count_by_direction.0 += 1;
            }
            Direction::Sell => {
                self.volume_by_direction.1 += volume;
                self.dollar_by_direction.1 += dollar;
                self.tick_count_by_direction.1 += 1;
            }
        }

        // 更新不平衡/运行值
        self.update_theta(tick, direction);

        // 更新bar的OHLCV
        if let Some(bar) = &mut self.current_bar {
            bar.close = tick.price;
            bar.high = bar.high.max(tick.price);
            bar.low = bar.low.min(tick.price);
            bar.volume += tick.volume;
        }
    }

    fn update_theta(&mut self, tick: &Tick, direction: Direction) {
        let sign = direction.sign() as f64;
        
        match self.bar_type {
            InformationDrivenBarType::TickImbalance => {
                self.theta += sign;
            }
            InformationDrivenBarType::VolumeImbalance => {
                self.theta += sign * tick.volume as f64;
            }
            InformationDrivenBarType::DollarImbalance => {
                self.theta += sign * tick.price * tick.volume as f64;
            }
            InformationDrivenBarType::TickRun => {
                // 对于run bars，使用最大运行计数
                let buy_count = self.tick_count_by_direction.0 as f64;
                let sell_count = self.tick_count_by_direction.1 as f64;
                self.theta = buy_count.max(sell_count);
            }
            InformationDrivenBarType::VolumeRun => {
                let buy_vol = self.volume_by_direction.0;
                let sell_vol = self.volume_by_direction.1;
                self.theta = buy_vol.max(sell_vol);
            }
            InformationDrivenBarType::DollarRun => {
                let buy_dollar = self.dollar_by_direction.0;
                let sell_dollar = self.dollar_by_direction.1;
                self.theta = buy_dollar.max(sell_dollar);
            }
        }
    }

    fn should_close_bar(&self) -> bool {
        let total_ticks = self.tick_count_by_direction.0 + self.tick_count_by_direction.1;
        
        if total_ticks < 1 {
            return false;
        }

        let expected_length = if self.expected_bar_length.is_initialized() {
            self.expected_bar_length.get()
        } else {
            total_ticks as f64
        };

        match self.bar_type {
            InformationDrivenBarType::TickImbalance => {
                let buy_prob = if self.buy_probability.is_initialized() {
                    self.buy_probability.get()
                } else {
                    self.tick_count_by_direction.0 as f64 / total_ticks as f64
                };
                let threshold = expected_length * (2.0 * buy_prob - 1.0).abs();
                self.theta.abs() >= threshold
            }
            InformationDrivenBarType::VolumeImbalance => {
                let buy_vol_exp = if self.buy_volume_expectation.is_initialized() {
                    self.buy_volume_expectation.get()
                } else {
                    self.volume_by_direction.0 / (self.tick_count_by_direction.0.max(1) as f64)
                };
                let sell_vol_exp = if self.sell_volume_expectation.is_initialized() {
                    self.sell_volume_expectation.get()
                } else {
                    self.volume_by_direction.1 / (self.tick_count_by_direction.1.max(1) as f64)
                };
                let buy_prob = self.tick_count_by_direction.0 as f64 / total_ticks as f64;
                let threshold = expected_length * (2.0 * buy_prob * buy_vol_exp - buy_prob * buy_vol_exp - (1.0 - buy_prob) * sell_vol_exp).abs();
                self.theta.abs() >= threshold
            }
            InformationDrivenBarType::DollarImbalance => {
                let buy_dollar_exp = if self.buy_dollar_expectation.is_initialized() {
                    self.buy_dollar_expectation.get()
                } else {
                    self.dollar_by_direction.0 / (self.tick_count_by_direction.0.max(1) as f64)
                };
                let sell_dollar_exp = if self.sell_dollar_expectation.is_initialized() {
                    self.sell_dollar_expectation.get()
                } else {
                    self.dollar_by_direction.1 / (self.tick_count_by_direction.1.max(1) as f64)
                };
                let buy_prob = self.tick_count_by_direction.0 as f64 / total_ticks as f64;
                let threshold = expected_length * (2.0 * buy_prob * buy_dollar_exp - buy_prob * buy_dollar_exp - (1.0 - buy_prob) * sell_dollar_exp).abs();
                self.theta.abs() >= threshold
            }
            InformationDrivenBarType::TickRun => {
                let buy_prob = self.tick_count_by_direction.0 as f64 / total_ticks as f64;
                let threshold = expected_length * buy_prob.max(1.0 - buy_prob);
                self.theta >= threshold
            }
            InformationDrivenBarType::VolumeRun => {
                let buy_vol_exp = if self.buy_volume_expectation.is_initialized() {
                    self.buy_volume_expectation.get()
                } else {
                    self.volume_by_direction.0 / (self.tick_count_by_direction.0.max(1) as f64)
                };
                let sell_vol_exp = if self.sell_volume_expectation.is_initialized() {
                    self.sell_volume_expectation.get()
                } else {
                    self.volume_by_direction.1 / (self.tick_count_by_direction.1.max(1) as f64)
                };
                let buy_prob = self.tick_count_by_direction.0 as f64 / total_ticks as f64;
                let threshold = expected_length * (buy_prob * buy_vol_exp).max((1.0 - buy_prob) * sell_vol_exp);
                self.theta >= threshold
            }
            InformationDrivenBarType::DollarRun => {
                let buy_dollar_exp = if self.buy_dollar_expectation.is_initialized() {
                    self.buy_dollar_expectation.get()
                } else {
                    self.dollar_by_direction.0 / (self.tick_count_by_direction.0.max(1) as f64)
                };
                let sell_dollar_exp = if self.sell_dollar_expectation.is_initialized() {
                    self.sell_dollar_expectation.get()
                } else {
                    self.dollar_by_direction.1 / (self.tick_count_by_direction.1.max(1) as f64)
                };
                let buy_prob = self.tick_count_by_direction.0 as f64 / total_ticks as f64;
                let threshold = expected_length * (buy_prob * buy_dollar_exp).max((1.0 - buy_prob) * sell_dollar_exp);
                self.theta >= threshold
            }
        }
    }

    fn close_current_bar(&mut self) -> Option<Bar> {
        if let Some(mut bar) = self.current_bar.take() {
            // 更新参数估计器
            let total_ticks = (self.tick_count_by_direction.0 + self.tick_count_by_direction.1) as f64;
            if total_ticks > 0.0 {
                self.expected_bar_length.update(total_ticks);
                
                let buy_prob = self.tick_count_by_direction.0 as f64 / total_ticks;
                self.buy_probability.update(buy_prob);
                
                if self.tick_count_by_direction.0 > 0 {
                    let avg_buy_vol = self.volume_by_direction.0 / (self.tick_count_by_direction.0 as f64);
                    self.buy_volume_expectation.update(avg_buy_vol);
                    let avg_buy_dollar = self.dollar_by_direction.0 / (self.tick_count_by_direction.0 as f64);
                    self.buy_dollar_expectation.update(avg_buy_dollar);
                }
                
                if self.tick_count_by_direction.1 > 0 {
                    let avg_sell_vol = self.volume_by_direction.1 / (self.tick_count_by_direction.1 as f64);
                    self.sell_volume_expectation.update(avg_sell_vol);
                    let avg_sell_dollar = self.dollar_by_direction.1 / (self.tick_count_by_direction.1 as f64);
                    self.sell_dollar_expectation.update(avg_sell_dollar);
                }
            }

            if let Some(start_time) = self.bar_start_time {
                bar.timestamp = start_time;
            }
            
            Some(bar)
        } else {
            None
        }
    }

    pub fn close(&mut self) -> Option<Bar> {
        self.current_bar.take()
    }

    pub fn get_current_bar(&self) -> Option<&Bar> {
        self.current_bar.as_ref()
    }
}
