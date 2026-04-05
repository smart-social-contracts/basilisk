import { getCanisterId, runTests } from '../../../_test_lib';
import { getTests } from './tests';
import { createActor } from './dfx_generated/threshold_ecdsa';

const tecdsaCanister = createActor(getCanisterId('threshold_ecdsa'), {
    agentOptions: {
        host: 'http://127.0.0.1:8000'
    }
});

runTests(getTests(tecdsaCanister));
