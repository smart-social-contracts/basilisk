import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister uninstall-code simple_erc20 || true`, {
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
