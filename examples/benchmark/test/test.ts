import { createActor } from './dfx_generated/benchmark';
import { HttpAgent } from '@dfinity/agent';
import { readFileSync, writeFileSync } from 'fs';
import { join } from 'path';

function getCanisterId(name: string): string {
    const idsPath = join(__dirname, '..', '.dfx', 'local', 'canister_ids.json');
    const ids = JSON.parse(readFileSync(idsPath, 'utf-8'));
    return ids[name].local;
}

interface BenchmarkResult {
    name: string;
    category: string;
    input_size: number;
    elapsed_ms: number;
    result: string;
}

async function timeit(
    name: string,
    category: string,
    input_size: number,
    fn: () => Promise<any>
): Promise<BenchmarkResult> {
    const start = performance.now();
    const result = await fn();
    const elapsed_ms = Math.round((performance.now() - start) * 100) / 100;
    const resultStr = typeof result === 'bigint' ? result.toString() : String(result);
    console.log(`  ${name}: ${elapsed_ms}ms`);
    return { name, category, input_size, elapsed_ms, result: resultStr };
}

async function main() {
    const backend = process.env.BASILISK_PYTHON_BACKEND || 'rustpython';
    console.log(`\n=== Benchmark: ${backend} backend ===\n`);

    const agent = new HttpAgent({ host: 'http://127.0.0.1:8000' });
    await agent.fetchRootKey();

    const canister = createActor(getCanisterId('benchmark'), { agent });

    const results: BenchmarkResult[] = [];

    // --- Pure Python compute benchmarks ---
    console.log('--- fibonacci (integer math) ---');
    for (const n of [1000, 5000, 10000]) {
        results.push(
            await timeit(`fibonacci(${n})`, 'compute', n, () =>
                canister.fibonacci(BigInt(n))
            )
        );
    }

    console.log('--- string_processing (string alloc/concat) ---');
    for (const n of [500, 1000, 2000]) {
        results.push(
            await timeit(`string_processing(${n})`, 'compute', n, () =>
                canister.string_processing(BigInt(n))
            )
        );
    }

    console.log('--- dict_operations (dict create/iterate) ---');
    for (const n of [500, 1000, 2000]) {
        results.push(
            await timeit(`dict_operations(${n})`, 'compute', n, () =>
                canister.dict_operations(BigInt(n))
            )
        );
    }

    console.log('--- json_roundtrip (JSON encode/decode) ---');
    for (const n of [100, 500, 1000]) {
        results.push(
            await timeit(`json_roundtrip(${n})`, 'compute', n, () =>
                canister.json_roundtrip(BigInt(n))
            )
        );
    }

    console.log('--- sort_benchmark (list sort) ---');
    for (const n of [1000, 5000, 10000]) {
        results.push(
            await timeit(`sort_benchmark(${n})`, 'compute', n, () =>
                canister.sort_benchmark(BigInt(n))
            )
        );
    }

    console.log('--- list_comprehension (nested list creation) ---');
    for (const n of [100, 200, 300]) {
        results.push(
            await timeit(`list_comprehension(${n})`, 'compute', n, () =>
                canister.list_comprehension(BigInt(n))
            )
        );
    }

    // --- StableBTreeMap IO benchmarks ---
    console.log('--- clear_db ---');
    await canister.clear_db();

    console.log('--- bulk_insert (stable memory write) ---');
    for (const n of [50, 100, 200]) {
        await canister.clear_db();
        results.push(
            await timeit(`bulk_insert(${n})`, 'io', n, () =>
                canister.bulk_insert(BigInt(n))
            )
        );
    }

    console.log('--- bulk_read (stable memory read) ---');
    await canister.clear_db();
    await canister.bulk_insert(BigInt(200));
    for (const n of [50, 100, 200]) {
        results.push(
            await timeit(`bulk_read(${n})`, 'io', n, () =>
                canister.bulk_read(BigInt(n))
            )
        );
    }

    // --- Output results ---
    const output = {
        backend,
        timestamp: new Date().toISOString(),
        results
    };

    const filename = `benchmark_results_${backend}.json`;
    writeFileSync(filename, JSON.stringify(output, null, 2));
    console.log(`\nResults written to ${filename}`);

    // Print summary table
    console.log(`\n=== Summary (${backend}) ===`);
    console.log(`${'Name'.padEnd(30)} ${'Category'.padEnd(10)} ${'ms'.padStart(10)}`);
    console.log('-'.repeat(52));
    for (const r of results) {
        console.log(
            `${r.name.padEnd(30)} ${r.category.padEnd(10)} ${r.elapsed_ms.toString().padStart(10)}`
        );
    }
}

main();
