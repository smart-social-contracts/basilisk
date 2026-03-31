import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister uninstall-code complex_init || true`, {
        stdio: 'inherit'
    });

    execSync(
        `icp deploy --argument 'record {"Oh hello there user"; record { id = "1" }}' complex_init`,
        {
            stdio: 'inherit'
        }
    );

    execSync(`icp generate`, {
        stdio: 'inherit'
    });
}

pretest();
