import { Test } from '../../_test_lib';

export function getTests(canister1: any, canister2: any, canister3: any): Test[] {
    return [
        {
            name: 'canister1 set and get',
            test: async () => {
                await canister1.stable_map_0_insert(0, 'value0');
                const result = await canister1.stable_map_0_get(0);
                return { Ok: result !== undefined && result !== null };
            }
        },
        {
            name: 'canister1 contains_key',
            test: async () => {
                const result = await canister1.stable_map_0_contains_key(0);
                return { Ok: result === true };
            }
        },
        {
            name: 'canister2 set and get',
            test: async () => {
                await canister2.stable_map_5_insert(5n, 'value5');
                const result = await canister2.stable_map_5_get(5n);
                return { Ok: result !== undefined && result !== null };
            }
        },
        {
            name: 'canister3 set and get',
            test: async () => {
                await canister3.stable_map_10_insert('key10', 10n);
                const result = await canister3.stable_map_10_get('key10');
                return { Ok: result !== undefined && result !== null };
            }
        }
    ];
}
