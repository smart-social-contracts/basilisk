import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister uninstall-code stable_memory || true`, {
        stdio: 'inherit'
    });

    execSync(`icp deploy`, {
        stdio: 'inherit'
    });

    execSync(`icp generate`, {
        stdio: 'inherit'
    });

    execSync(
        `icp ledger fabricate-cycles --canister stable_memory --cycles 100000000000000`,
        {
            stdio: 'inherit'
        }
    );
}

pretest();
