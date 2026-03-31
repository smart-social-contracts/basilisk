import { getCanisterId } from 'azle/test';
import { execSync } from 'child_process';

async function pretest() {

    execSync(`icp deploy some_service`, {
        stdio: 'inherit'
    });
    execSync(`bash ../../scripts/sync-canister-ids.sh`, {
        stdio: 'inherit'
    });


    execSync(
        `icp canister install rejections --args '(principal "${getCanisterId(
            'some_service'
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
