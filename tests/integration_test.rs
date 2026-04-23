// tests/integration_test.rs
// 集成测试

#[cfg(test)]
mod tests {
    use Bars::types::Tick;
    use chrono::Utc;
    use csv;

    #[test]
    fn test_tick_creation() {
        let tick = Tick {
            timestamp: Utc::now(),
            price: 100.0,
            volume: 10,
        };
        assert_eq!(tick.price, 100.0);
    }

    #[test]
    fn test_csv_io() {
        let input_path = "/home/lhh/Documents/lhhrustprojects/bars/data/DOGEUSDT-aggTrades-2026-03.csv";
        let output_path = "/home/lhh/Documents/lhhrustprojects/bars/data/test.csv";

        let mut reader = csv::ReaderBuilder::new()
            .has_headers(true)
            .from_path(input_path)
            .expect("Failed to open input CSV");

        let headers = reader.headers().expect("Failed to read headers").clone();

        let records: Vec<csv::StringRecord> = reader.records().filter_map(|r| r.ok()).collect();
        let last_5: Vec<_> = records.into_iter().rev().take(5).rev().collect();

        let mut writer = csv::Writer::from_path(output_path).expect("Failed to create output CSV");
        writer.write_record(&headers).ok();
        for record in last_5 {
            writer.write_record(&record).ok();
        }
        writer.flush().ok();

        let mut verify_reader = csv::ReaderBuilder::new().has_headers(true).from_path(output_path).unwrap();
        let count = verify_reader.records().count();
        assert_eq!(count, 5);
    }
}