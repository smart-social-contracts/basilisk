import { execSync } from 'child_process';

async function pretest() {
    execSync(
        `icp canister uninstall-code init_and_post_upgrade_recovery || true`,
        {
            stdio: 'inherit'
        }
    );

    execSync(`icp canister create init_and_post_upgrade_recovery`, {
        stdio: 'inherit'
    });

    execSync(`icp build init_and_post_upgrade_recovery`, {
        stdio: 'inherit'
    });

    execSync(`icp generate init_and_post_upgrade_recovery`, {
        stdio: 'inherit'
    });
}

pretest();
