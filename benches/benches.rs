// benches/benches.rs
// 性能基准测试

use criterion::{black_box, criterion_group, criterion_main, Criterion};

fn bench_example(c: &mut Criterion) {
    c.bench_function("example", |b| b.iter(|| black_box(42)));
}

criterion_group!(benches, bench_example);
criterion_main!(benches);