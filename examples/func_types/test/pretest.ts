import { getCanisterId } from 'azle/test';
import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister uninstall-code func_types || true`, {
        stdio: 'inherit'
    });

    execSync(`icp canister uninstall-code notifiers || true`, {
        stdio: 'inherit'
    });

    execSync(`icp deploy notifiers`, {
        stdio: 'inherit'
    });

    execSync(
        `icp deploy func_types --argument '(principal "${getCanisterId(
            'notifiers'
        )}")'`,
        {
            stdio: 'inherit'
        }
    );

    execSync(`icp generate`, {
        stdio: 'inherit'
    });
}

pretest();
