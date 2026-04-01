import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister create init_and_post_upgrade_recovery`, {
        stdio: 'inherit'
    });

    execSync(`icp build init_and_post_upgrade_recovery`, {
        stdio: 'inherit'
    });

    execSync(`bash ../../scripts/icp-generate.sh init_and_post_upgrade_recovery`, {
        stdio: 'inherit'
    });
}

pretest();
