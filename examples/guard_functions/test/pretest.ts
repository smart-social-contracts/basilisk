import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp deploy guard_functions`, {
        stdio: 'inherit'
    });

    execSync(`bash ../../scripts/icp-generate.sh`, {
        stdio: 'inherit'
    });
}

pretest();
