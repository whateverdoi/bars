// src/bars.rs
// 实现各类Bars的聚合逻辑

use crate::types::{Tick, Bar};
use chrono::{DateTime, Duration, TimeZone, Utc};

#[derive(Debug, Clone, Copy)]
pub enum BarType {
    // 标准bars
    Time(Duration),
    Tick(u64),
    Volume(u64),
    Dollar(f64),
    
    // 信息驱动bars
    TickImbalance,
    VolumeImbalance,
    DollarImbalance,
    TickRun,
    VolumeRun,
    DollarRun,
}

impl BarType {
    pub fn time(seconds: i64) -> Self {
        BarType::Time(Duration::seconds(seconds))
    }

    pub fn tick_count(count: u64) -> Self {
        BarType::Tick(count)
    }

    pub fn volume(volume: u64) -> Self {
        BarType::Volume(volume)
    }

    pub fn dollar(amount: f64) -> Self {
        BarType::Dollar(amount)
    }
}

pub struct BarAggregator {
    bar_type: BarType,
    current_bar: Option<Bar>,
    tick_count: u64,
    volume_sum: f64,
    dollar_sum: f64,
    bar_start_time: Option<DateTime<Utc>>,
    bar_open_time: Option<DateTime<Utc>>,
}

impl BarAggregator {
    pub fn new(bar_type: BarType) -> Self {
        Self {
            bar_type,
            current_bar: None,
            tick_count: 0,
            volume_sum: 0.0,
            dollar_sum: 0.0,
            bar_start_time: None,
            bar_open_time: None,
        }
    }

    pub fn add_tick(&mut self, tick: Tick) -> Option<Bar> {
        let should_close = self.should_close_bar(&tick);
        
        if should_close {
            let closed_bar = self.close_current_bar();
            self.start_new_bar(tick);
            closed_bar
        } else {
            self.update_current_bar(tick);
            None
        }
    }

    pub fn get_current_bar(&self) -> Option<&Bar> {
        self.current_bar.as_ref()
    }

    fn should_close_bar(&self, tick: &Tick) -> bool {
        if self.current_bar.is_none() {
            return true;
        }

        match self.bar_type {
            BarType::Time(duration) => {
                if let Some(open_time) = self.bar_open_time {
                    tick.timestamp.signed_duration_since(open_time) >= duration
                } else {
                    true
                }
            }
            BarType::Tick(count) => self.tick_count >= count,
            BarType::Volume(vol) => self.volume_sum >= vol as f64,
            BarType::Dollar(amount) => self.dollar_sum >= amount,
            // 信息驱动的bar类型不应该在这里处理
            BarType::TickImbalance | BarType::VolumeImbalance | BarType::DollarImbalance |
            BarType::TickRun | BarType::VolumeRun | BarType::DollarRun => {
                panic!("Information-driven bar types should be handled by ImbalanceBarAggregator")
            }
        }
    }

    fn start_new_bar(&mut self, tick: Tick) {
        self.bar_start_time = Some(tick.timestamp);
        self.bar_open_time = Some(self.round_to_period(tick.timestamp));
        self.tick_count = 1;
        self.volume_sum = tick.volume;
        self.dollar_sum = tick.price * tick.volume;

        self.current_bar = Some(Bar {
            open: tick.price,
            high: tick.price,
            low: tick.price,
            close: tick.price,
            volume: tick.volume,
            timestamp: tick.timestamp,
        });
    }

    fn round_to_period(&self, timestamp: DateTime<Utc>) -> DateTime<Utc> {
        match self.bar_type {
            BarType::Time(duration) => {
                let period_ms = duration.num_milliseconds();
                let ts = timestamp.timestamp_millis();
                let rounded = (ts / period_ms) * period_ms;
                Utc.timestamp_millis_opt(rounded).single().unwrap_or(timestamp)
            }
            _ => timestamp,
        }
    }

    fn update_current_bar(&mut self, tick: Tick) {
        self.tick_count += 1;
        self.volume_sum += tick.volume;
        self.dollar_sum += tick.price * tick.volume;

        if let Some(bar) = &mut self.current_bar {
            bar.close = tick.price;
            bar.high = bar.high.max(tick.price);
            bar.low = bar.low.min(tick.price);
            bar.volume += tick.volume;
        }
    }

    fn close_current_bar(&mut self) -> Option<Bar> {
        if let Some(bar) = &mut self.current_bar {
            if let Some(open_time) = self.bar_open_time {
                bar.timestamp = open_time;
            }
        }
        self.current_bar.take()
    }

    pub fn close(&mut self) -> Option<Bar> {
        self.close_current_bar()
    }
}
