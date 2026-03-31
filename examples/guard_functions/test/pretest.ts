import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister uninstall-code guard_functions || true`, {
        stdio: 'inherit'
    });

    execSync(`icp deploy guard_functions`, {
        stdio: 'inherit'
    });

    execSync(`icp generate`, {
        stdio: 'inherit'
    });
}

pretest();
