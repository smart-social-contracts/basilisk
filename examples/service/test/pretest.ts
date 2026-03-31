import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister uninstall-code rejections || true`, {
        stdio: 'inherit'
    });

    execSync(`icp canister uninstall-code some_service || true`, {
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
