import { getCanisterId, runTests } from '../../../_test_lib';
import { getTests } from './tests';
import { createActor } from './dfx_generated/simple_to_do';

const simpleToDoCanister = createActor(getCanisterId('simple_to_do'), {
    agentOptions: {
        host: 'http://127.0.0.1:8000'
    }
});

runTests(getTests(simpleToDoCanister));
