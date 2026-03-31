import { getCanisterId } from 'azle/test';
import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister uninstall-code rejections || true`, {
        stdio: 'inherit'
    });

    execSync(`icp canister uninstall-code some_service || true`, {
        stdio: 'inherit'
    });

    execSync(`icp deploy some_service`, {
        stdio: 'inherit'
    });

    execSync(
        `icp deploy rejections --argument '(principal "${getCanisterId(
            'some_service'
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
