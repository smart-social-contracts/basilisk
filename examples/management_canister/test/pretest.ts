import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister uninstall-code management_canister || true`, {
        stdio: 'inherit'
    });

    execSync(`icp deploy management_canister`, {
        stdio: 'inherit'
    });

    execSync(
        `icp ledger fabricate-cycles --canister management_canister --cycles 100000000000000`,
        {
            stdio: 'inherit'
        }
    );

    execSync(`icp generate management_canister`, {
        stdio: 'inherit'
    });
}

pretest();
