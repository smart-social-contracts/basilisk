import { getCanisterId, runTests } from '../../_test_lib';
import { getTests, BitcoinState } from './tests';
import { createActor } from './dfx_generated/bitcoin';

// TODO: The bitcoin example requires local wallets, bitcoin_cli, and impureSetup helpers.
// These were previously imported from azle/examples/bitcoin/test/ and need to be
// provided locally when the bitcoin test infrastructure is set up.

const bitcoinCanister = createActor(getCanisterId('bitcoin'), {
    agentOptions: {
        host: 'http://127.0.0.1:8000'
    }
});

const state: BitcoinState = {
    signedTxHex: ''
};

// Placeholder wallets and bitcoinCli — replace with local implementations
const wallets = {
    alice: { p2wpkh: '' },
    bob: { p2wpkh: '' }
};

const bitcoinCli = {
    getReceivedByAddress: (_address: string, _minconf?: number) => 0,
    generateToAddress: (_blocks: number, _address: string) => {}
};

runTests(getTests(bitcoinCanister, state, wallets, bitcoinCli));
