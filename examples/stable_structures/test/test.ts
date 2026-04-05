import { getCanisterId, runTests } from '../../_test_lib';
import { getTests } from './tests';
import { createActor as createActorCanister1 } from './dfx_generated/canister1';
import { createActor as createActorCanister2 } from './dfx_generated/canister2';
import { createActor as createActorCanister3 } from './dfx_generated/canister3';

const stableStructuresCanister1 = createActorCanister1(
    getCanisterId('canister1'),
    { agentOptions: { host: 'http://127.0.0.1:8000' } }
);

const stableStructuresCanister2 = createActorCanister2(
    getCanisterId('canister2'),
    { agentOptions: { host: 'http://127.0.0.1:8000' } }
);

const stableStructuresCanister3 = createActorCanister3(
    getCanisterId('canister3'),
    { agentOptions: { host: 'http://127.0.0.1:8000' } }
);

runTests(
    getTests(
        stableStructuresCanister1,
        stableStructuresCanister2,
        stableStructuresCanister3
    )
);
