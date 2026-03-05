import { createSnakeCaseProxy, getCanisterId, runTests } from 'azle/test';
import { getTests } from 'azle/examples/ic_api/test/tests';
import { createActor } from './dfx_generated/ic_api';

const icApiCanister = createActor(getCanisterId('ic_api'), {
    agentOptions: {
        host: 'http://127.0.0.1:8000'
    }
});

runTests(
    getTests(createSnakeCaseProxy(icApiCanister)).map((test) => {
        if (test.name === 'trap') {
            return {
                ...test,
                test: async () => {
                    try {
                        const result = await icApiCanister.trap(
                            'here is the message'
                        );
                        return {
                            Ok: result
                        };
                    } catch (error: any) {
                        return {
                            Ok: error.props.Message.includes('here is the message')
                        };
                    }
                }
            };
        }
        return test;
    })
);
