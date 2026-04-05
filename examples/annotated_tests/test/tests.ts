import { Test } from '../../_test_lib';

export function getTests(annotatedCanister: any): Test[] {
    return [
        {
            name: 'is_empty',
            test: async () => {
                return {
                    Ok: await annotatedCanister.is_empty()
                };
            }
        },
        {
            name: 'get_type_alias',
            test: async () => {
                return {
                    Ok: await annotatedCanister.get_type_alias()
                };
            }
        },
        {
            name: 'get_func',
            test: async () => {
                const result = await annotatedCanister.get_func();

                return {
                    Ok: result[1] === 'create_canister'
                };
            }
        }
    ];
}
