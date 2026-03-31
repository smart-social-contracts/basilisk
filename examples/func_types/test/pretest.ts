import { getCanisterId } from 'azle/test';
import { execSync } from 'child_process';

async function pretest() {

    execSync(`icp deploy notifiers`, {
        stdio: 'inherit'
    });
    execSync(`bash ../../scripts/sync-canister-ids.sh`, {
        stdio: 'inherit'
    });


    execSync(
        `icp canister create func_types`, {
        stdio: 'inherit'
    });

    execSync(`icp build func_types`, {
        stdio: 'inherit'
    });

    execSync(`icp canister install func_types --args '(principal "${getCanisterId(
            'notifiers'
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
