import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister uninstall-code persistent-storage || true`, {
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
