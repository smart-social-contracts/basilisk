import { Test } from '../../_test_lib';

export function getTests(tupleTypesCanister: any): Test[] {
    return [
        {
            name: 'tuple_of_one',
            test: async () => {
                const result = await tupleTypesCanister.tuple_of_one();
                return { Ok: result !== undefined };
            }
        },
        {
            name: 'two_tuple',
            test: async () => {
                const result = await tupleTypesCanister.two_tuple();
                return { Ok: Array.isArray(result) && result.length === 2 };
            }
        },
        {
            name: 'three_tuple',
            test: async () => {
                const result = await tupleTypesCanister.three_tuple();
                return { Ok: Array.isArray(result) && result.length === 3 };
            }
        }
        // twoTupleWithInlineRecords excluded — Kybra does not have the concept of inline records
    ];
}
