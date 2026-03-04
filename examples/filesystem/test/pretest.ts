import { execSync } from 'child_process';

async function pretest() {
    execSync(`dfx canister uninstall-code filesystem || true`, {
        stdio: 'inherit'
    });

    execSync(`dfx deploy filesystem`, {
        stdio: 'inherit'
    });

    execSync(`dfx generate filesystem`, {
        stdio: 'inherit'
    });
}

pretest();
