import { execSync } from 'child_process';
import { someonePrincipal } from './tests';

async function pretest() {
    execSync(`icp deploy whoami`, {
        stdio: 'inherit'
    });

    execSync(
        `icp canister install whoami --args '(principal "${someonePrincipal}")' --mode reinstall --yes`,
        {
            stdio: 'inherit'
        }
    );

    execSync(`bash ../../../scripts/icp-generate.sh`, {
        stdio: 'inherit'
    });
}

pretest();
