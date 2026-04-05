import { Test } from '../../_test_lib';

export function getTests(lolCanister: any): Test[] {
    return [
        {
            name: 'list_of_string_one',
            test: async () => {
                const result = await lolCanister.list_of_string_one(['hello', 'world']);
                return { Ok: result.length === 2 && result[0] === 'hello' && result[1] === 'world' };
            }
        },
        {
            name: 'list_of_string_two',
            test: async () => {
                const input = [['a', 'b'], ['c']];
                const result = await lolCanister.list_of_string_two(input);
                return {
                    Ok: result.length === 2 && result[0][0] === 'a' && result[1][0] === 'c'
                };
            }
        },
        {
            name: 'list_of_bool',
            test: async () => {
                const input = [[[true, false]]];
                const result = await lolCanister.list_of_bool(input);
                return {
                    Ok: result[0][0][0] === true && result[0][0][1] === false
                };
            }
        },
        {
            name: 'list_of_null',
            test: async () => {
                const input = [[[null, null]]];
                const result = await lolCanister.list_of_null(input);
                return {
                    Ok: result[0][0][0] === null && result[0][0][1] === null
                };
            }
        },
        {
            name: 'list_of_nat8',
            test: async () => {
                const input = [[[1, 2, 3]]];
                const result = await lolCanister.list_of_nat8(input);
                return {
                    Ok: result[0][0][0] === 1 && result[0][0][2] === 3
                };
            }
        },
        {
            name: 'list_of_record',
            test: async () => {
                const input = [[[{ name: 'Alice', age: 30 }]]];
                const result = await lolCanister.list_of_record(input);
                return {
                    Ok: result[0][0][0].name === 'Alice' && result[0][0][0].age === 30
                };
            }
        },
        {
            name: 'list_of_variant',
            test: async () => {
                const input = [[[{ solid: null }]]];
                const result = await lolCanister.list_of_variant(input);
                return { Ok: 'solid' in result[0][0][0] };
            }
        }
    ];
}
