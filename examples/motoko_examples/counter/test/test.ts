import { getCanisterId, runTests } from 'azle/test';
import { getTests } from 'azle/examples/motoko_examples/counter/test/tests';
import { createActor } from './dfx_generated/counter';
import { HttpAgent } from '@dfinity/agent';

async function main() {
    const agent = new HttpAgent({ host: 'http://127.0.0.1:8000' });
    await agent.fetchRootKey();

    const counterCanister = createActor(getCanisterId('counter'), {
        agent
    });

    runTests(getTests(counterCanister as any));
}

main();
