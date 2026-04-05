import { getCanisterId, runTests } from '../../../_test_lib';
import { getTests } from './tests';
import { createActor } from './dfx_generated/persistent_storage';

const persistentStorageCanister = createActor(
    getCanisterId('persistent_storage'),
    {
        agentOptions: {
            host: 'http://127.0.0.1:8000'
        }
    }
);

runTests(getTests(persistentStorageCanister));
