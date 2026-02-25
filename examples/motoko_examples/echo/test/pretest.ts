import { execSync } from 'child_process';
import { readFileSync } from 'fs';

async function pretest() {
    const dfxConfig = JSON.parse(readFileSync('dfx.json', 'utf-8'));
    const canisterName = Object.keys(dfxConfig.canisters)[0];

    // Try regular deploy. On a system subnet with fast enough hardware,
    // this completes within the dfx ingress timeout (~5 min).
    try {
        execSync('dfx deploy', { stdio: 'inherit' });
        execSync('dfx generate', { stdio: 'inherit' });
        return;
    } catch {
        console.log(
            `Deploy failed/timed out for ${canisterName}. ` +
            'Polling for background completion on system subnet...'
        );
    }

    // On a system subnet (no instruction limit), the IC replica continues
    // processing install_code even after the dfx ingress timeout expires.
    // Poll canister status until the module hash appears.
    const maxWaitMs = 20 * 60 * 1000; // 20 minutes
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
        `Canister ${canisterName} did not install within 20 minutes`
    );
}

pretest();
