import { execSync } from 'child_process';

async function pretest() {
    try {
        execSync(`dfx canister uninstall-code query || true`, {
            stdio: 'inherit',
            timeout: 60_000
        });
    } catch {}

    // CPython wasm is large (~3.6MB) and PocketIC native compilation may
    // exceed dfx's 5-minute ingress timeout. Strategy:
    // 1. Submit deploy (will likely timeout)
    // 2. PocketIC continues compiling in background
    // 3. Poll canister status until module hash appears
    try {
        execSync(`dfx deploy`, { stdio: 'inherit' });
        execSync(`dfx generate`, { stdio: 'inherit' });
        return;
    } catch {
        console.log('Deploy timed out — PocketIC still compiling wasm...');
    }

    // Poll for up to 20 minutes until PocketIC finishes compilation
    const maxWaitSec = 1200;
    const pollSec = 30;
    let installed = false;

    for (let waited = 0; waited < maxWaitSec; waited += pollSec) {
        execSync(`sleep ${pollSec}`);
        try {
            const out = execSync(`dfx canister status query 2>&1`, {
                timeout: 15_000
            }).toString();
            if (out.includes('Module hash: 0x')) {
                console.log(`Canister installed after ~${waited + pollSec}s`);
                installed = true;
                break;
            }
        } catch {
            console.log(`Waiting for PocketIC... (${waited + pollSec}s/${maxWaitSec}s)`);
        }
    }

    if (!installed) {
        // Final attempt after PocketIC should have finished
        execSync(`dfx deploy`, { stdio: 'inherit' });
    }

    execSync(`dfx generate`, { stdio: 'inherit' });
}

pretest();
