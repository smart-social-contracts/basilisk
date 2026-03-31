import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp deploy stdlib`, {
        stdio: 'inherit'
    });

    execSync(`bash ../../scripts/icp-generate.sh stdlib`, {
        stdio: 'inherit'
    });
}

pretest();
