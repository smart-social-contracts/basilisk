import { createSnakeCaseProxy, getCanisterId, runTests, Test } from 'azle/test';
import { getTests } from 'azle/examples/manual_reply/test/tests';
import { createActor } from './dfx_generated/manual_reply';

const manualReplyCanister = createActor(getCanisterId('manual_reply'), {
    agentOptions: {
        host: 'http://127.0.0.1:8000'
    }
});

const proxy = createSnakeCaseProxy(manualReplyCanister);
const tests: Test[] = getTests(proxy).map((t: Test) => {
    // Basilisk correctly encodes void as () -> () so the agent returns undefined,
    // not null. The azle tests expect null due to a self-described incorrect
    // candid return type generation in azle/kybra.
    if (t.name === 'update reply with void' || t.name === 'query reply with void') {
        return {
            ...t,
            test: async () => {
                const method = t.name.includes('update') ? 'updateVoid' : 'queryVoid';
                const result = await (proxy as any)[method]();
                return { Ok: result === undefined };
            }
        };
    }
    return t;
});

runTests(tests);
