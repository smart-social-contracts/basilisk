import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister create complex_init`, {
        stdio: 'inherit'
    });

    execSync(`icp build complex_init`, {
        stdio: 'inherit'
    });

    execSync(
        `icp canister install complex_init --args 'record {"Oh hello there user"; record { id = "1" }}' --mode reinstall --yes`,
        {
            stdio: 'inherit'
        }
    );

    execSync(`bash ../../scripts/icp-generate.sh`, {
        stdio: 'inherit'
    });
}

pretest();
