import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister uninstall-code http_counter || true`, {
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
