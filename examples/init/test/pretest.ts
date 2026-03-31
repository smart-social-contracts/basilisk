import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp deploy init`, {
        stdio: 'inherit'
    });

    execSync(
        `icp canister install init --args '(record { id = "0" }, variant { Fire }, principal "rrkah-fqaaa-aaaaa-aaaaq-cai")' --mode reinstall --yes`,
        {
            stdio: 'inherit'
        }
    );

    execSync(`bash ../../scripts/icp-generate.sh`, {
        stdio: 'inherit'
    });
}

pretest();
