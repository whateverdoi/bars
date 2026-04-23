use Bars::bars::{BarAggregator, BarType};
use Bars::types::Tick;
use chrono::{TimeZone, Utc};
use clap::{Parser, ValueEnum};
use std::fs::File;

#[derive(Parser)]
#[command(name = "bars")]
#[command(about = "聚合交易数据生成Bars")]
struct Cli {
    #[arg(short, long)]
    input: String,

    #[arg(short, long, default_value = "output.csv")]
    output: String,

    #[arg(short, long, default_value = "1m")]
    bar_type: BarTypeArg,
}

#[derive(Clone, ValueEnum)]
enum BarTypeArg {
    Time1S,
    Time1M,
    Time5M,
    Time15M,
    Time1H,
    Tick100,
    Tick500,
    Volume,
    Dollar,
}

impl Cli {
    fn to_bar_type(&self) -> BarType {
        match self.bar_type {
            BarTypeArg::Time1S => BarType::time(1),
            BarTypeArg::Time1M => BarType::time(60),
            BarTypeArg::Time5M => BarType::time(300),
            BarTypeArg::Time15M => BarType::time(900),
            BarTypeArg::Time1H => BarType::time(3600),
            BarTypeArg::Tick100 => BarType::tick_count(100),
            BarTypeArg::Tick500 => BarType::tick_count(500),
            BarTypeArg::Volume => BarType::volume(1000000),
            BarTypeArg::Dollar => BarType::dollar(10000.0),
        }
    }
}

fn main() {
    let cli = Cli::parse();
    println!("Reading: {}", cli.input);

    let mut reader = csv::ReaderBuilder::new()
        .has_headers(true)
        .from_path(&cli.input)
        .expect("Failed to open input CSV");

    let _headers = reader.headers().expect("Failed to read headers").clone();

    let mut aggregator = BarAggregator::new(cli.to_bar_type());
    let mut bars: Vec<String> = Vec::new();

    for result in reader.records() {
        if let Ok(record) = result {
            let price: f64 = record.get(1).unwrap_or("0").parse().unwrap_or(0.0);
            let volume: f64 = record.get(2).unwrap_or("0").parse().unwrap_or(0.0);
            let transact_time: i64 = record.get(5).unwrap_or("0").parse().unwrap_or(0);

            let timestamp = Utc.timestamp_millis_opt(transact_time).single().unwrap_or_else(Utc::now);
            let tick = Tick::new(timestamp, price, volume as u64);

            if let Some(bar) = aggregator.add_tick(tick) {
                let line = format!(
                    "{},{},{},{},{},{}",
                    bar.timestamp.format("%Y-%m-%d %H:%M:%S%.3f"),
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                    bar.volume
                );
                bars.push(line);
            }
        }
    }

    if let Some(bar) = aggregator.close() {
        let line = format!(
            "{},{},{},{},{},{}",
            bar.timestamp.format("%Y-%m-%d %H:%M:%S%.3f"),
            bar.open,
            bar.high,
            bar.low,
            bar.close,
            bar.volume
        );
        bars.push(line);
    }

    let bar_count = bars.len();
    let mut output = File::create(&cli.output).expect("Failed to create output");
    use std::io::Write;
    writeln!(output, "timestamp,open,high,low,close,volume").unwrap();
    for bar in &bars {
        writeln!(output, "{}", bar).unwrap();
    }

    println!("Written {} bars to {}", bar_count, cli.output);
}