import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister uninstall-code tuple_types || true`, {
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
