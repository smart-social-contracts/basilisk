import { getCanisterId, runTests } from '../../_test_lib';
import { getTests } from './tests';
import { createActor } from './dfx_generated/primitive_types';

const primitiveTypesCanister = createActor(getCanisterId('primitive_types'), {
    agentOptions: {
        host: 'http://127.0.0.1:8000'
    }
});

runTests(getTests(primitiveTypesCanister));
