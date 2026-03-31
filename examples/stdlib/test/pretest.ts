import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister uninstall-code stdlib || true`, {
        stdio: 'inherit'
    });

    execSync(`icp deploy stdlib`, {
        stdio: 'inherit'
    });

    execSync(`icp generate stdlib`, {
        stdio: 'inherit'
    });
}

pretest();
