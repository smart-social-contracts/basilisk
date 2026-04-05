import { Test } from '../../_test_lib';

export function getTests(nullCanister: any): Test[] {
    return [
        {
            name: 'null_function',
            test: async () => {
                const result = await nullCanister.null_function(null);
                return { Ok: result === null };
            }
        },
        {
            name: 'void_is_not_null',
            test: async () => {
                await nullCanister.void_is_not_null();
                return { Ok: true };
            }
        },
        {
            name: 'get_partially_null_record',
            test: async () => {
                const result = await nullCanister.get_partially_null_record();
                return {
                    Ok:
                        result.first_item === 1 &&
                        result.second_item === null &&
                        result.third_item === 3
                };
            }
        },
        {
            name: 'set_partially_null_record',
            test: async () => {
                const input = { first_item: 5, second_item: null, third_item: 10 };
                const result = await nullCanister.set_partially_null_record(input);
                return {
                    Ok:
                        result.first_item === 5 &&
                        result.second_item === null &&
                        result.third_item === 10
                };
            }
        },
        {
            name: 'get_small_null_record',
            test: async () => {
                const result = await nullCanister.get_small_null_record();
                return {
                    Ok: result.first_item === null && result.second_item === null
                };
            }
        },
        {
            name: 'set_small_null_record',
            test: async () => {
                const input = { first_item: null, second_item: null };
                const result = await nullCanister.set_small_null_record(input);
                return {
                    Ok: result.first_item === null && result.second_item === null
                };
            }
        },
        {
            name: 'get_large_null_record',
            test: async () => {
                const result = await nullCanister.get_large_null_record();
                return {
                    Ok:
                        result.first_item === null &&
                        result.second_item === null &&
                        result.third_item === null
                };
            }
        },
        {
            name: 'set_large_null_record',
            test: async () => {
                const input = { first_item: null, second_item: null, third_item: null };
                const result = await nullCanister.set_large_null_record(input);
                return {
                    Ok:
                        result.first_item === null &&
                        result.second_item === null &&
                        result.third_item === null
                };
            }
        }
    ];
}
