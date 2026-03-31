import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister uninstall-code null_example || true`, {
        stdio: 'inherit'
    });

    execSync(`icp deploy null_example`, {
        stdio: 'inherit'
    });

    execSync(`icp generate`, {
        stdio: 'inherit'
    });
}

pretest();
