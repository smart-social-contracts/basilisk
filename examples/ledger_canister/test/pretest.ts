import { getCanisterId } from 'azle/test';
import { execSync } from 'child_process';

async function pretest(icp_ledger_path: string) {

    execSync(`mkdir -p ${icp_ledger_path}`, {
        stdio: 'inherit'
    });

    execSync(
        `cd ${icp_ledger_path} && curl -o ledger.wasm.gz https://download.dfinity.systems/ic/149b6208cbbb61e8142a069dd7a046d349beaf7a/canisters/ledger-canister_notify-method.wasm.gz`,
        {
            stdio: 'inherit'
        }
    );

    execSync(`cd ${icp_ledger_path} && gunzip -f ledger.wasm.gz`, {
        stdio: 'inherit'
    });

    execSync(
        `cd ${icp_ledger_path} && curl -o ledger.private.did https://raw.githubusercontent.com/dfinity/ic/dfdba729414d3639b2a6c269600bbbd689b35385/rs/rosetta-api/ledger.did`,
        {
            stdio: 'inherit'
        }
    );

    execSync(
        `cd ${icp_ledger_path} && curl -o ledger.public.did https://raw.githubusercontent.com/dfinity/ic/dfdba729414d3639b2a6c269600bbbd689b35385/rs/rosetta-api/ledger_canister/ledger.did`,
        {
            stdio: 'inherit'
        }
    );

    execSync(`icp canister create ledger_canister`, {
        stdio: 'inherit'
    });

    execSync(`icp canister create icp_ledger`, {
        stdio: 'inherit'
    });

    execSync(`icp build icp_ledger`, {
        stdio: 'inherit'
    });

    execSync(`bash ../../scripts/sync-canister-ids.sh`, {
        stdio: 'inherit'
    });

    // Pre-compute account IDs to avoid nested bash substitution issues
    const mintingAccount = execSync(`icp identity account-id`)
        .toString()
        .trim();

    // Read ledger_canister principal from icp CLI mapping file
    const fs = require('fs');
    const mappingsPath = '.icp/cache/mappings/local.ids.json';
    const mappings = JSON.parse(fs.readFileSync(mappingsPath, 'utf8'));
    const ledgerCanisterPrincipal = mappings['ledger_canister'];

    const ledgerAccount = execSync(
        `icp identity account-id --of-principal ${ledgerCanisterPrincipal}`
    )
        .toString()
        .trim();

    execSync(
        `icp canister install icp_ledger --args '(record {minting_account = "${mintingAccount}"; initial_values = vec { record { "${ledgerAccount}"; record { e8s=100_000_000_000 } }; }; send_whitelist = vec {}})' --mode reinstall --yes`,
        {
            stdio: 'inherit'
        }
    );

    execSync(`bash ../../scripts/sync-canister-ids.sh`, {
        stdio: 'inherit'
    });

    execSync(`icp build ledger_canister`, {
        stdio: 'inherit'
    });

    execSync(
        `icp canister install ledger_canister --args '(principal "${getCanisterId(
            'icp_ledger'
        )}")' --mode reinstall --yes`,
        {
            stdio: 'inherit'
        }
    );

    execSync(`bash ../../scripts/icp-generate.sh ledger_canister`, {
        stdio: 'inherit'
    });
}

pretest('src/icp_ledger');
