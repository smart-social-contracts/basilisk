import { getCanisterId, runTests } from '../../_test_lib';
import { getTests } from './tests';
import { createActor } from './dfx_generated/annotated_tests';

const annotatedCanister = createActor(getCanisterId('annotated_tests'), {
    agentOptions: {
        host: 'http://127.0.0.1:8000'
    }
});

runTests(getTests(annotatedCanister));
