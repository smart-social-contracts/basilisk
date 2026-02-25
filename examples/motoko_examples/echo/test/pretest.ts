import { execSync } from 'child_process';

async function pretest() {
    execSync(`dfx canister uninstall-code echo || true`, {
        stdio: 'inherit'
    });

    // CPython wasm is large (~3.8MB) and PocketIC native compilation may
    // exceed dfx's 5-minute request timeout. Retry with wait between attempts.
    const maxAttempts = 3;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            execSync(`dfx deploy`, { stdio: 'inherit' });
            break;
        } catch (e) {
            if (attempt === maxAttempts) throw e;
            console.error(`Deploy attempt ${attempt}/${maxAttempts} timed out, waiting 120s for PocketIC...`);
            execSync('sleep 120');
        }
    }

    execSync(`dfx generate`, {
        stdio: 'inherit'
    });
}

pretest();
