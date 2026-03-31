import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp deploy`, {
        stdio: 'inherit'
    });
    execSync(`bash ../../scripts/icp-generate.sh`, {
        stdio: 'inherit'
    });
}

pretest();
