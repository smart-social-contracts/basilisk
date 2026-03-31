import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister uninstall-code canister1 || true`, {
        stdio: 'inherit'
    });

    execSync(`icp canister uninstall-code canister2 || true`, {
        stdio: 'inherit'
    });

    execSync(`icp canister uninstall-code canister3 || true`, {
        stdio: 'inherit'
    });

    execSync(`icp deploy`, {
        stdio: 'inherit'
    });

    execSync(`icp generate`, {
        stdio: 'inherit'
    });
}

pretest();
