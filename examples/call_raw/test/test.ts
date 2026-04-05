import { getCanisterId, runTests } from '../../_test_lib';
import { getTests } from './tests';
import { createActor } from './dfx_generated/call_raw';

const callRawCanister = createActor(getCanisterId('call_raw'), {
    agentOptions: {
        host: 'http://127.0.0.1:8000'
    }
});

runTests(getTests(callRawCanister));
