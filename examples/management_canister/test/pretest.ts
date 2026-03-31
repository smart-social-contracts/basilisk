import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp deploy management_canister`, {
        stdio: 'inherit'
    });

    // Note: icp CLI local network provides cycles automatically

    execSync(`bash ../../scripts/icp-generate.sh management_canister`, {
        stdio: 'inherit'
    });
}

pretest();
