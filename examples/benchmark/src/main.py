from basilisk import query, text, nat64


# === Pure Python compute benchmarks ===

@query
def fibonacci(n: nat64) -> nat64:
    """Iterative fibonacci - pure integer math."""
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a % (2**64)


@query
def string_processing(n: nat64) -> text:
    """String manipulation - allocations, concatenation, formatting."""
    result = ""
    for i in range(n):
        result = f"item_{i}:" + str(i * 17 % 1000) + ";" + result[:200]
    return result[:100]


@query
def dict_operations(n: nat64) -> nat64:
    """Dictionary creation, lookup, iteration."""
    d = {}
    for i in range(n):
        d[f"key_{i}"] = {"value": i, "label": f"item_{i}", "tags": [i, i + 1, i + 2]}
    total = 0
    for k, v in d.items():
        total += v["value"] + sum(v["tags"])
    return total


@query
def json_roundtrip(n: nat64) -> text:
    """JSON encode/decode cycle - tests _json C accelerator."""
    import json

    data = [
        {"id": i, "name": f"entity_{i}", "values": list(range(10))} for i in range(n)
    ]
    encoded = json.dumps(data)
    decoded = json.loads(encoded)
    return f"items={len(decoded)},bytes={len(encoded)}"


@query
def sort_benchmark(n: nat64) -> nat64:
    """List sort - Timsort."""
    data = [(i * 2654435761) % (n + 1) for i in range(n)]
    data.sort()
    return data[n // 2] if n > 0 else 0


@query
def list_comprehension(n: nat64) -> nat64:
    """Nested list comprehension - object creation overhead."""
    matrix = [[i * j for j in range(n)] for i in range(n)]
    return sum(sum(row) for row in matrix)
