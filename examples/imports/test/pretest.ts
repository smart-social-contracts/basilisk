import { execSync } from 'child_process';

async function pretest() {
    execSync(`pip install boltons==23.0.0`, {
        stdio: 'inherit'
    });
    execSync(`icp deploy`, {
        stdio: 'inherit'
    });

    execSync(`bash ../../scripts/icp-generate.sh`, {
        stdio: 'inherit'
    });
}

pretest();
