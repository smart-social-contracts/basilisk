import { getCanisterId, runTests } from '../../../_test_lib';
import { createActor } from './dfx_generated/whoami';
import { callingIdentity, getTests } from './tests';

const whoamiCanister = createActor(getCanisterId('whoami'), {
    agentOptions: {
        host: 'http://127.0.0.1:8000',
        identity: callingIdentity
    }
});

runTests(getTests(whoamiCanister, 'whoami'));
