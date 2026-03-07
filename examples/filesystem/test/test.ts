import { getCanisterId, runTests } from 'azle/test';
import { createActor } from './dfx_generated/filesystem';
import { getTests } from './tests';
import { HttpAgent } from '@dfinity/agent';

async function main() {
    const agent = new HttpAgent({ host: 'http://127.0.0.1:8000' });
    await agent.fetchRootKey();

    const filesystemCanister = createActor(getCanisterId('filesystem'), {
        agent
    });

    runTests(getTests(filesystemCanister));
}

main();
