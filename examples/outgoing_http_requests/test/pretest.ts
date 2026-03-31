import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister uninstall-code outgoing_http_requests || true`, {
        stdio: 'inherit'
    });

    execSync(`icp deploy`, {
        stdio: 'inherit'
    });

    execSync(`icp generate`, {
        stdio: 'inherit'
    });
}

pretest();
