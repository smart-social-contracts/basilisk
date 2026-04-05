import { getCanisterId, runTests } from '../../_test_lib';
import { getTests } from './tests';
import { createActor } from './dfx_generated/inspect_message';

const inspectMessageCanister = createActor(getCanisterId('inspect_message'), {
    agentOptions: {
        host: 'http://127.0.0.1:8000'
    }
});

runTests(getTests(inspectMessageCanister));
