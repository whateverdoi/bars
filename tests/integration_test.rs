// tests/integration_test.rs
// 集成测试

#[cfg(test)]
mod tests {
    use bars::bars::{BarAggregator, BarType};
    use bars::information_driven::{ImbalanceBarAggregator, InformationDrivenBarType};
    use bars::types::Tick;
    use chrono::{TimeZone, Utc};
    use csv;

    #[test]
    fn test_tick_creation() {
        let tick = Tick {
            timestamp: Utc::now(),
            price: 100.0,
            volume: 10.0,
            direction: None,
        };
        assert_eq!(tick.price, 100.0);
    }

    #[test]
    fn test_csv_io() {
        let input_path =
            "/home/lhh/Documents/lhhrustprojects/bars/data/DOGEUSDT-aggTrades-2026-03.csv";
        let output_path = "/home/lhh/Documents/lhhrustprojects/bars/data/test.csv";

        let mut reader = csv::ReaderBuilder::new()
            .has_headers(true)
            .from_path(input_path)
            .expect("Failed to open input CSV");

        let headers = reader.headers().expect("Failed to read headers").clone();

        let records: Vec<csv::StringRecord> = reader.records().filter_map(|r| r.ok()).collect();
        println!("数据一共有{}行", records.len());
        let last_5: Vec<_> = records.into_iter().rev().take(5).rev().collect();

        let mut writer = csv::Writer::from_path(output_path).expect("Failed to create output CSV");
        writer.write_record(&headers).ok();
        for record in last_5 {
            writer.write_record(&record).ok();
        }
        writer.flush().ok();

        let mut verify_reader = csv::ReaderBuilder::new()
            .has_headers(true)
            .from_path(output_path)
            .unwrap();
        let count = verify_reader.records().count();
        assert_eq!(count, 5);
    }

    #[test]
    fn test_standard_bar_close_aligns_timestamp_to_period() {
        let mut aggregator = BarAggregator::new(BarType::time(60));
        let tick = Tick::new(
            Utc.with_ymd_and_hms(2026, 3, 1, 0, 0, 5).unwrap(),
            100.0,
            1.25,
        );

        let _ = aggregator.add_tick(tick);
        let bar = aggregator.close().expect("expected final time bar");

        assert_eq!(
            bar.timestamp,
            Utc.with_ymd_and_hms(2026, 3, 1, 0, 0, 0).unwrap()
        );
        assert_eq!(bar.volume, 1.25);
    }

    #[test]
    fn test_info_driven_close_discards_incomplete_bar() {
        let mut aggregator =
            ImbalanceBarAggregator::new(InformationDrivenBarType::TickImbalance, 0.2);
        let tick = Tick::new(
            Utc.with_ymd_and_hms(2026, 3, 1, 0, 0, 5).unwrap(),
            100.0,
            1.25,
        );

        let _ = aggregator.add_tick(tick);
        assert!(aggregator.close().is_none());
    }
}
