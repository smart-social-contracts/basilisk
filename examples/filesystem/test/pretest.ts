import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister uninstall-code filesystem || true`, {
        stdio: 'inherit'
    });

    execSync(`icp deploy filesystem`, {
        stdio: 'inherit'
    });

    execSync(`icp generate filesystem`, {
        stdio: 'inherit'
    });
}

pretest();
