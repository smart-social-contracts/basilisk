import { getCanisterId, runTests } from '../../../_test_lib';
import { getTests } from './tests';
import { createActor } from './dfx_generated/echo';

const echoCanister = createActor(getCanisterId('echo'), {
    agentOptions: {
        host: 'http://127.0.0.1:8000'
    }
});

runTests(getTests(echoCanister));
