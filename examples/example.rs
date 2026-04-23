// examples/example.rs
// 示例代码

use bars::types::Tick;
use chrono::Utc;

fn main() {
    let tick = Tick {
        timestamp: Utc::now(),
        price: 100.0,
        volume: 10.0,
        direction: None,
    };
    println!("Tick: {:?}", tick);
}
