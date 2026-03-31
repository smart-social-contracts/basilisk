import { execSync } from 'child_process';

async function pretest() {
    execSync(`pip install boltons==23.0.0`, {
        stdio: 'inherit'
    });

    execSync(`icp canister uninstall-code imports || true`, {
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
