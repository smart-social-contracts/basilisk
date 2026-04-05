/**
 * Minimal test utilities for Basilisk examples.
 * Replaces the azle/test dependency with a self-contained solution.
 */

import { execSync } from 'child_process';
import { readFileSync } from 'fs';
import { join } from 'path';

// ---- Types ----------------------------------------------------------------

export interface Test {
    name: string;
    test?: () => Promise<{ Ok?: boolean; Err?: string }>;
    prep?: () => Promise<void>;
    wait?: number;
    skip?: boolean;
}

// ---- Test runner -----------------------------------------------------------

export async function runTests(tests: Test[]): Promise<void> {
    let passed = 0;
    let failed = 0;
    let skipped = 0;

    for (const t of tests) {
        if (t.skip) {
            console.log(`  SKIP: ${t.name}`);
            skipped++;
            continue;
        }
        if (t.wait) {
            console.log(`  WAIT: ${t.name} (${t.wait}ms)`);
            await new Promise((resolve) => setTimeout(resolve, t.wait));
            continue;
        }
        if (t.prep) {
            try {
                console.log(`  PREP: ${t.name}`);
                await t.prep();
            } catch (e: any) {
                console.log(`  FAIL (prep): ${t.name} — ${e.message || e}`);
                failed++;
            }
            continue;
        }
        if (!t.test) {
            console.log(`  SKIP: ${t.name} — no test function`);
            skipped++;
            continue;
        }
        try {
            const result = await t.test();
            if ('Ok' in result) {
                if (result.Ok) {
                    console.log(`  PASS: ${t.name}`);
                    passed++;
                } else {
                    console.log(`  FAIL: ${t.name} — Ok was false`);
                    failed++;
                }
            } else if ('Err' in result) {
                console.log(`  FAIL: ${t.name} — ${result.Err}`);
                failed++;
            }
        } catch (e: any) {
            console.log(`  FAIL: ${t.name} — ${e.message || e}`);
            failed++;
        }
    }

    console.log(`\n${passed} passed, ${failed} failed, ${skipped} skipped`);
    if (failed > 0) {
        process.exit(1);
    }
}

// ---- Canister ID discovery -------------------------------------------------

export function getCanisterId(name: string): string {
    // Try .dfx/local first (PocketIC / local replica)
    for (const candidate of [
        join('.dfx', 'local', 'canister_ids.json'),
        'canister_ids.json',
    ]) {
        try {
            const ids = JSON.parse(readFileSync(candidate, 'utf-8'));
            if (ids[name]?.local) return ids[name].local;
            if (ids[name]?.ic) return ids[name].ic;
        } catch {}
    }
    throw new Error(`Cannot find canister ID for "${name}"`);
}

// ---- Snake-case proxy ------------------------------------------------------

/**
 * Creates a proxy that transparently converts camelCase property access
 * to snake_case, so azle-style test code works with basilisk's snake_case
 * method names.
 */
export function createSnakeCaseProxy<T extends object>(actor: T): T {
    return new Proxy(actor, {
        get(target: any, prop: string | symbol) {
            if (typeof prop === 'string') {
                // Convert camelCase → snake_case
                const snakeCase = prop.replace(
                    /[A-Z]/g,
                    (m) => `_${m.toLowerCase()}`
                );
                if (snakeCase !== prop && snakeCase in target) {
                    return target[snakeCase];
                }
            }
            return target[prop];
        },
    }) as T;
}

// ---- Result helpers --------------------------------------------------------

export function ok<T>(result: any): result is { Ok: T } {
    return result != null && 'Ok' in result;
}

// ---- dfx CLI helpers -------------------------------------------------------

/**
 * Run `dfx identity whoami` and return the identity name.
 */
export function whoami(): string {
    return execSync('dfx identity whoami').toString().trim();
}

/**
 * Run `dfx identity get-principal` for the given identity (or current)
 * and return the principal string.
 */
export function getPrincipal(identity?: string): string {
    const cmd = identity
        ? `dfx --identity ${identity} identity get-principal`
        : 'dfx identity get-principal';
    return execSync(cmd).toString().trim();
}
