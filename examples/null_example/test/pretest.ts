import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp deploy null_example`, {
        stdio: 'inherit'
    });

    execSync(`bash ../../scripts/icp-generate.sh`, {
        stdio: 'inherit'
    });
}

pretest();
