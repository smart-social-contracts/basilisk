use candid::CandidType;
use ic_cdk::{query, update};
use std::cell::RefCell;

#[derive(CandidType)]
struct BenchmarkResult {
    body_instructions: u64,
    total_instructions: u64,
    result: u64,
}

#[derive(CandidType)]
struct BenchmarkResultText {
    body_instructions: u64,
    total_instructions: u64,
    result: String,
}

thread_local! {
    static COUNT: RefCell<u64> = RefCell::new(0);
}

#[query]
fn bench_noop() -> BenchmarkResult {
    let start = ic_cdk::api::performance_counter(0);
    let end = ic_cdk::api::performance_counter(0);
    BenchmarkResult {
        body_instructions: end - start,
        total_instructions: ic_cdk::api::performance_counter(1),
        result: 0,
    }
}

#[update]
fn bench_increment() -> BenchmarkResult {
    let start = ic_cdk::api::performance_counter(0);
    let val = COUNT.with(|c| {
        let mut c = c.borrow_mut();
        *c += 1;
        *c
    });
    let end = ic_cdk::api::performance_counter(0);
    BenchmarkResult {
        body_instructions: end - start,
        total_instructions: ic_cdk::api::performance_counter(1),
        result: val,
    }
}

#[query]
fn bench_fibonacci() -> BenchmarkResult {
    let start = ic_cdk::api::performance_counter(0);
    let mut a: u64 = 0;
    let mut b: u64 = 1;
    for _ in 0..25 {
        let tmp = b;
        b = a + b;
        a = tmp;
    }
    let end = ic_cdk::api::performance_counter(0);
    BenchmarkResult {
        body_instructions: end - start,
        total_instructions: ic_cdk::api::performance_counter(1),
        result: a,
    }
}

fn fib_recursive(n: u64) -> u64 {
    if n <= 1 {
        return n;
    }
    fib_recursive(n - 1) + fib_recursive(n - 2)
}

#[query]
fn bench_fibonacci_recursive() -> BenchmarkResult {
    let start = ic_cdk::api::performance_counter(0);
    let result = fib_recursive(20);
    let end = ic_cdk::api::performance_counter(0);
    BenchmarkResult {
        body_instructions: end - start,
        total_instructions: ic_cdk::api::performance_counter(1),
        result,
    }
}

#[query]
fn bench_string_ops() -> BenchmarkResultText {
    let start = ic_cdk::api::performance_counter(0);
    let mut s = String::new();
    for i in 0..100u64 {
        s.push_str(&i.to_string());
    }
    let result: String = s.chars().take(50).collect();
    let end = ic_cdk::api::performance_counter(0);
    BenchmarkResultText {
        body_instructions: end - start,
        total_instructions: ic_cdk::api::performance_counter(1),
        result,
    }
}

#[query]
fn bench_list_ops() -> BenchmarkResult {
    let start = ic_cdk::api::performance_counter(0);
    let mut lst: Vec<u64> = Vec::new();
    for i in 0..500u64 {
        lst.push(500 - i);
    }
    lst.sort();
    let end = ic_cdk::api::performance_counter(0);
    BenchmarkResult {
        body_instructions: end - start,
        total_instructions: ic_cdk::api::performance_counter(1),
        result: lst[0],
    }
}

#[query]
fn bench_dict_ops() -> BenchmarkResult {
    let start = ic_cdk::api::performance_counter(0);
    let mut map = std::collections::HashMap::new();
    for i in 0..500u64 {
        map.insert(i.to_string(), i * i);
    }
    let mut total: u64 = 0;
    for i in 0..500u64 {
        total += map[&i.to_string()];
    }
    let end = ic_cdk::api::performance_counter(0);
    BenchmarkResult {
        body_instructions: end - start,
        total_instructions: ic_cdk::api::performance_counter(1),
        result: total,
    }
}

#[query]
fn bench_method_overhead() -> BenchmarkResult {
    BenchmarkResult {
        body_instructions: 0,
        total_instructions: ic_cdk::api::performance_counter(1),
        result: 0,
    }
}

#[query]
fn bench_sum_to() -> BenchmarkResult {
    let start = ic_cdk::api::performance_counter(0);
    let mut total: u64 = 0;
    for i in 1..=10000u64 {
        total += i;
    }
    let end = ic_cdk::api::performance_counter(0);
    BenchmarkResult {
        body_instructions: end - start,
        total_instructions: ic_cdk::api::performance_counter(1),
        result: total,
    }
}

fn ackermann(m: u64, n: u64) -> u64 {
    if m == 0 {
        return n + 1;
    }
    if n == 0 {
        return ackermann(m - 1, 1);
    }
    ackermann(m - 1, ackermann(m, n - 1))
}

#[query]
fn bench_ackermann() -> BenchmarkResult {
    let start = ic_cdk::api::performance_counter(0);
    let result = ackermann(3, 6);
    let end = ic_cdk::api::performance_counter(0);
    BenchmarkResult {
        body_instructions: end - start,
        total_instructions: ic_cdk::api::performance_counter(1),
        result,
    }
}
