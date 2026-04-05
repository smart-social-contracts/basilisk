import { Test } from '../../_test_lib';

export function getTests(canister1: any): Test[] {
    return [
        {
            name: 'simple_composite_query test',
            test: async () => {
                const result = await canister1.simple_composite_query();
                return { Ok: 'Ok' in result && result.Ok === 'Hello from Canister 2' };
            }
        },
        {
            name: 'manual_query test',
            test: async () => {
                const result = await canister1.manual_query();
                return { Ok: 'Ok' in result };
            }
        },
        {
            name: 'totally_manual_query test',
            test: async () => {
                const result = await canister1.totally_manual_query();
                return { Ok: 'Ok' in result };
            }
        },
        {
            name: 'deep_query test',
            test: async () => {
                const result = await canister1.deep_query();
                return { Ok: 'Ok' in result };
            }
        },
        {
            name: 'inc_counter test',
            test: async () => {
                const result = await canister1.inc_counter();
                return { Ok: typeof result === 'bigint' };
            }
        },
        {
            name: 'inc_canister1 test',
            test: async () => {
                const result = await canister1.inc_canister1();
                return { Ok: 'Ok' in result && result.Ok === 3n };
            }
        },
        {
            name: 'inc_canister2 test',
            test: async () => {
                const result = await canister1.inc_canister2();
                return { Ok: 'Ok' in result };
            }
        }
    ];
}
