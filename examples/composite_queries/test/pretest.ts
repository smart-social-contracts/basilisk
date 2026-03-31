import { getCanisterId } from 'azle/test';
import { execSync } from 'child_process';

async function pretest() {


    execSync(`icp deploy canister3`, {
        stdio: 'inherit'
    });
    execSync(`bash ../../scripts/sync-canister-ids.sh`, {
        stdio: 'inherit'
    });


    execSync(
        `icp canister install canister2 --args '(principal "${getCanisterId(
            'canister3'
        )}")' --mode reinstall --yes`,
        {
            stdio: 'inherit'
        }
    );

    execSync(
        `icp canister install canister1 --args '(principal "${getCanisterId(
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
