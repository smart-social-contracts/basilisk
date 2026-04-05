import { getCanisterId, runTests } from '../../_test_lib';
import { getTests } from './tests';
import { createActor } from './dfx_generated/guard_functions';

const functionGuardCanister = createActor(getCanisterId('guard_functions'), {
    agentOptions: {
        host: 'http://127.0.0.1:8000'
    }
});

runTests(getTests(functionGuardCanister));
