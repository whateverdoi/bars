// src/types.rs
// 定义Tick和Bar数据结构

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Direction {
    Buy,   // 买单
    Sell,  // 卖单
}

impl Direction {
    pub fn sign(&self) -> i32 {
        match self {
            Direction::Buy => 1,
            Direction::Sell => -1,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Tick {
    pub timestamp: DateTime<Utc>,
    pub price: f64,
    pub volume: u64,
    #[serde(skip)]
    pub direction: Option<Direction>,
}

impl Tick {
    pub fn new(timestamp: DateTime<Utc>, price: f64, volume: u64) -> Self {
        Self { 
            timestamp, 
            price, 
            volume,
            direction: None,
        }
    }

    pub fn with_direction(mut self, direction: Direction) -> Self {
        self.direction = Some(direction);
        self
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Bar {
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: u64,
    pub timestamp: DateTime<Utc>,
}

impl Bar {
    pub fn new(open: f64, high: f64, low: f64, close: f64, volume: u64, timestamp: DateTime<Utc>) -> Self {
        Self { open, high, low, close, volume, timestamp }
    }
}

/// 指数加权移动平均 (EWMA) 计算器
#[derive(Debug, Clone)]
pub struct EWMACalculator {
    value: f64,
    alpha: f64,
    is_initialized: bool,
}

impl EWMACalculator {
    /// 创建一个新的EWMA计算器
    /// alpha: 平滑系数 (0 < alpha <= 1)，越小越平滑
    pub fn new(alpha: f64) -> Self {
        assert!(alpha > 0.0 && alpha <= 1.0, "alpha must be in (0, 1]");
        Self {
            value: 0.0,
            alpha,
            is_initialized: false,
        }
    }

    /// 更新EMA值
    pub fn update(&mut self, new_value: f64) {
        if !self.is_initialized {
            self.value = new_value;
            self.is_initialized = true;
        } else {
            self.value = self.alpha * new_value + (1.0 - self.alpha) * self.value;
        }
    }

    /// 获取当前的EMA值
    pub fn get(&self) -> f64 {
        self.value
    }

    /// 重置计算器
    pub fn reset(&mut self) {
        self.value = 0.0;
        self.is_initialized = false;
    }

    /// 检查是否已初始化
    pub fn is_initialized(&self) -> bool {
        self.is_initialized
    }
}