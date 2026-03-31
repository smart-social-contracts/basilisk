import { getCanisterId } from 'azle/test';
import { execSync } from 'child_process';

async function pretest() {

    execSync(`icp deploy cycles`, {
        stdio: 'inherit'
    });
    execSync(`bash ../../scripts/sync-canister-ids.sh`, {
        stdio: 'inherit'
    });


    execSync(
        `icp canister create intermediary`, {
        stdio: 'inherit'
    });

    execSync(`icp build intermediary`, {
        stdio: 'inherit'
    });

    execSync(`icp canister install intermediary --args '(principal "${getCanisterId(
            'cycles'
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
