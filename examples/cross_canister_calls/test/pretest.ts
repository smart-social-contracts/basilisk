import { getCanisterId } from 'azle/test';
import { execSync } from 'child_process';

async function pretest() {

    execSync(`icp deploy canister2`, {
        stdio: 'inherit'
    });
    execSync(`bash ../../scripts/sync-canister-ids.sh`, {
        stdio: 'inherit'
    });


    execSync(
        `icp canister create canister1`, {
        stdio: 'inherit'
    });

    execSync(`icp build canister1`, {
        stdio: 'inherit'
    });

    execSync(`icp canister install canister1 --args '(principal "${getCanisterId(
            'canister2'
        )}")' --mode reinstall --yes`,
        {
            stdio: 'inherit'
        }
    );

    execSync(`bash ../../scripts/icp-generate.sh`, {
        stdio: 'inherit'
    });
}

pretest();
