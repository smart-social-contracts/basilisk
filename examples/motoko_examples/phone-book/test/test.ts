import { getCanisterId, runTests } from '../../../_test_lib';
import { getTests } from './tests';
import { createActor } from './dfx_generated/phone_book';

const phoneBookCanister = createActor(getCanisterId('phone_book'), {
    agentOptions: {
        host: 'http://127.0.0.1:8000'
    }
});

runTests(getTests(phoneBookCanister));
