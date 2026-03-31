import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister uninstall-code ethereum_json_rpc || true`, {
        stdio: 'inherit'
    });

    execSync(
        `icp deploy --argument '("${process.env.ETHEREUM_URL}")' ethereum_json_rpc`,
        {
            stdio: 'inherit'
        }
    );

    execSync(`icp generate`, {
        stdio: 'inherit'
    });
}

pretest();
