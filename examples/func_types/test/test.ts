import { createSnakeCaseProxy, getCanisterId, runTests } from 'azle/test';
import { getTests } from 'azle/examples/func_types/test/tests';
import { createActor } from './dfx_generated/func_types';

const funcTypesCanister = createActor(getCanisterId('func_types'), {
    agentOptions: {
        host: 'http://127.0.0.1:8000'
    }
});

runTests(
    getTests(createSnakeCaseProxy(funcTypesCanister)).map((test) => {
        if (test.name === 'getNotifierFromNotifiersCanister') {
            return {
                name: 'getNotifierFromNotifiersCanister',
                test: async () => {
                    try {
                        const result =
                            await funcTypesCanister.get_notifier_from_notifiers_canister();
                        console.log(
                            'getNotifierFromNotifiersCanister: result =',
                            JSON.stringify(result, (_, v) =>
                                typeof v === 'bigint' ? v.toString() : v
                            )
                        );
                        if ('Err' in result) {
                            return { Err: result.Err };
                        }
                        return {
                            Ok:
                                result.Ok[0].toText() !== '' &&
                                result.Ok[1] === 'notify'
                        };
                    } catch (e: any) {
                        console.log(
                            'getNotifierFromNotifiersCanister: exception =',
                            e?.message ?? String(e)
                        );
                        return { Err: e?.message ?? String(e) };
                    }
                }
            };
        }
        return test;
    })
);
