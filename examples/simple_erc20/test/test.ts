import { getCanisterId, runTests } from '../../_test_lib';
import { getTests } from './tests';
import { createActor } from './dfx_generated/simple_erc20';

const simpleErc20Canister = createActor(getCanisterId('simple_erc20'), {
    agentOptions: {
        host: 'http://127.0.0.1:8000'
    }
});

runTests(getTests(simpleErc20Canister));
