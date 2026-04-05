import { getCanisterId, runTests } from '../../../_test_lib';
import { getTests } from './tests';
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
