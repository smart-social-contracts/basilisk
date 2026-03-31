import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp deploy filesystem`, {
        stdio: 'inherit'
    });

    execSync(`bash ../../scripts/icp-generate.sh filesystem`, {
        stdio: 'inherit'
    });
}

pretest();
