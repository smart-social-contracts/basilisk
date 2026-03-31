import { execSync } from 'child_process';
import { someonePrincipal } from './tests';

async function pretest() {
    execSync(`icp canister uninstall-code whoami || true`, {
        stdio: 'inherit'
    });

    execSync(
        `icp deploy --argument '(principal "${someonePrincipal}")' whoami`,
        {
            stdio: 'inherit'
        }
    );

    execSync(`icp generate`, {
        stdio: 'inherit'
    });
}

pretest();
