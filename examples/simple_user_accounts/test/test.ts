import { getCanisterId, runTests } from '../../_test_lib';
import { getTests } from './tests';
import { createActor } from './dfx_generated/simple_user_accounts';

const simple_user_accounts_canister = createActor(
    getCanisterId('simple_user_accounts'),
    {
        agentOptions: {
            host: 'http://127.0.0.1:8000'
        }
    }
);

runTests(getTests(simple_user_accounts_canister));
