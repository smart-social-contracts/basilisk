import { execSync } from 'child_process';
import { readFileSync } from 'fs';

async function pretest() {
    const dfxConfig = JSON.parse(readFileSync('dfx.json', 'utf-8'));
    const canisterName = Object.keys(dfxConfig.canisters)[0];

    // Try regular deploy. On an application subnet with DTS,
    // this may timeout but installation continues across rounds.
    try {
        execSync('dfx deploy', { stdio: 'inherit' });
        execSync('dfx generate', { stdio: 'inherit' });
        return;
    } catch {
        console.log(
            `Deploy failed/timed out for ${canisterName}. ` +
            'Polling for background completion (DTS across rounds)...'
        );
    }

    // With DTS (Deterministic Time Slicing), the replica splits wasm
    // compilation across rounds. Poll canister status until the module
    // hash appears, indicating installation completed.
    const maxWaitMs = 35 * 60 * 1000; // 35 minutes
    const pollMs = 15_000;
    const startTime = Date.now();

    while (Date.now() - startTime < maxWaitMs) {
        await new Promise(r => setTimeout(r, pollMs));
        const elapsed = Math.round((Date.now() - startTime) / 1000);
        try {
            const status = execSync(
                `dfx canister status ${canisterName} 2>&1`,
                { timeout: 15_000 }
            ).toString();
            if (status.includes('Module hash: 0x')) {
                console.log(`Canister ${canisterName} installed after ~${elapsed}s`);
                execSync('dfx generate', { stdio: 'inherit' });
                return;
            }
        } catch {}
        console.log(`Waiting for wasm installation... (${elapsed}s)`);
    }

    throw new Error(
        `Canister ${canisterName} did not install within 35 minutes`
    );
}

pretest();
