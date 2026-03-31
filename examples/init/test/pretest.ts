import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister uninstall-code init || true`, {
        stdio: 'inherit'
    });

    execSync(
        `icp deploy --argument '(record { id = "0" }, variant { Fire }, principal "rrkah-fqaaa-aaaaa-aaaaq-cai")' init`,
        {
            stdio: 'inherit'
        }
    );

    execSync(`icp generate`, {
        stdio: 'inherit'
    });
}

pretest();
