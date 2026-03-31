import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister uninstall-code pre_and_post_upgrade || true`, {
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
