from basilisk import ic, nat64, query, update, Record


class BenchmarkResult(Record):
    body_instructions: nat64
    total_instructions: nat64
    result: nat64


class BenchmarkResultText(Record):
    body_instructions: nat64
    total_instructions: nat64
    result: str


# ─── State ───────────────────────────────────────────────────────────────────

count: nat64 = 0


# ─── Benchmarks ──────────────────────────────────────────────────────────────


@query
def bench_noop() -> BenchmarkResult:
    """Baseline: measure the overhead of a method call itself."""
    start = ic.performance_counter(0)
    end = ic.performance_counter(0)
    return {
        "body_instructions": end - start,
        "total_instructions": ic.performance_counter(1),
        "result": 0,
    }


@update
def bench_increment() -> BenchmarkResult:
    """Measure a simple counter increment."""
    global count
    start = ic.performance_counter(0)
    count += 1
    end = ic.performance_counter(0)
    return {
        "body_instructions": end - start,
        "total_instructions": ic.performance_counter(1),
        "result": count,
    }


@query
def bench_fibonacci() -> BenchmarkResult:
    """Measure CPU-bound work: compute fib(25) iteratively."""
    start = ic.performance_counter(0)
    a, b = 0, 1
    for _ in range(25):
        a, b = b, a + b
    end = ic.performance_counter(0)
    return {
        "body_instructions": end - start,
        "total_instructions": ic.performance_counter(1),
        "result": a,
    }


@query
def bench_fibonacci_recursive() -> BenchmarkResult:
    """Measure recursive function calls: fib(20) recursively."""
    def fib(n: int) -> int:
        if n <= 1:
            return n
        return fib(n - 1) + fib(n - 2)

    start = ic.performance_counter(0)
    result = fib(20)
    end = ic.performance_counter(0)
    return {
        "body_instructions": end - start,
        "total_instructions": ic.performance_counter(1),
        "result": result,
    }


@query
def bench_string_ops() -> BenchmarkResultText:
    """Measure string concatenation and manipulation."""
    start = ic.performance_counter(0)
    s = ""
    for i in range(100):
        s += str(i)
    result = s[:50]
    end = ic.performance_counter(0)
    return {
        "body_instructions": end - start,
        "total_instructions": ic.performance_counter(1),
        "result": result,
    }


@query
def bench_list_ops() -> BenchmarkResult:
    """Measure list creation, append, sort."""
    start = ic.performance_counter(0)
    lst = []
    for i in range(500):
        lst.append(500 - i)
    lst.sort()
    end = ic.performance_counter(0)
    return {
        "body_instructions": end - start,
        "total_instructions": ic.performance_counter(1),
        "result": lst[0],
    }


@query
def bench_dict_ops() -> BenchmarkResult:
    """Measure dict creation and lookup."""
    start = ic.performance_counter(0)
    d = {}
    for i in range(500):
        d[str(i)] = i * i
    total = 0
    for i in range(500):
        total += d[str(i)]
    end = ic.performance_counter(0)
    return {
        "body_instructions": end - start,
        "total_instructions": ic.performance_counter(1),
        "result": total,
    }


@query
def bench_method_overhead() -> BenchmarkResult:
    """Measure the total instruction count for the entire method call (prelude + body)."""
    return {
        "body_instructions": 0,
        "total_instructions": ic.performance_counter(1),
        "result": 0,
    }
