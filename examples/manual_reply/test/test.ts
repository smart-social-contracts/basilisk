import { getCanisterId, runTests } from '../../_test_lib';
import { getTests } from './tests';
import { createActor } from './dfx_generated/manual_reply';

const manualReplyCanister = createActor(getCanisterId('manual_reply'), {
    agentOptions: {
        host: 'http://127.0.0.1:8000'
    }
});

runTests(getTests(manualReplyCanister));
