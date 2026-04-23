// src/types.rs
// 定义Tick和Bar数据结构

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Tick {
    pub timestamp: DateTime<Utc>,
    pub price: f64,
    pub volume: u64,
}

impl Tick {
    pub fn new(timestamp: DateTime<Utc>, price: f64, volume: u64) -> Self {
        Self { timestamp, price, volume }
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