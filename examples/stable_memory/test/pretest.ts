import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp deploy`, {
        stdio: 'inherit'
    });

    execSync(`bash ../../scripts/icp-generate.sh`, {
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
