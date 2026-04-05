import { Test } from '../../_test_lib';

export function getTests(funcTypesCanister: any): Test[] {
    return [
        {
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
        },
        {
            name: 'get_notifier',
            test: async () => {
                const result = await funcTypesCanister.get_notifier();
                return { Ok: Array.isArray(result) && result.length === 2 };
            }
        }
    ];
}
