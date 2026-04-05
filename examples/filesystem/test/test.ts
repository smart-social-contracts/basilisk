import { getCanisterId, runTests } from '../../_test_lib';
import { createActor } from './dfx_generated/filesystem';
import { getTests } from './tests';

const filesystemCanister = createActor(getCanisterId('filesystem'), {
    agentOptions: {
        host: 'http://127.0.0.1:8000'
    }
});

runTests(getTests(filesystemCanister));
