import { execSync } from 'child_process';

async function pretest() {
    execSync(`icp canister create ethereum_json_rpc`, {
        stdio: 'inherit'
    });

    execSync(`icp build ethereum_json_rpc`, {
        stdio: 'inherit'
    });

    execSync(
        `icp canister install ethereum_json_rpc --args '("${process.env.ETHEREUM_URL}")' --mode reinstall --yes`,
        {
            stdio: 'inherit'
        }
    );

    execSync(`bash ../../scripts/icp-generate.sh`, {
        stdio: 'inherit'
    });
}

pretest();
