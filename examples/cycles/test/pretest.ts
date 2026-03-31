import { getCanisterId } from 'azle/test';
import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister uninstall-code cycles || true`, {
        stdio: 'inherit'
    });

    execSync(`icp canister uninstall-code intermediary || true`, {
        stdio: 'inherit'
    });

    execSync(`icp deploy cycles`, {
        stdio: 'inherit'
    });

    execSync(
        `icp deploy intermediary --argument '(principal "${getCanisterId(
            'cycles'
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
