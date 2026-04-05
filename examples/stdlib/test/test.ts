import { getCanisterId, runTests } from '../../_test_lib';
import { createActor } from './dfx_generated/stdlib';
import { getTests } from './tests';

const stdlibCanister = createActor(getCanisterId('stdlib'), {
    agentOptions: {
        host: 'http://127.0.0.1:8000'
    }
});

runTests(getTests(stdlibCanister));
