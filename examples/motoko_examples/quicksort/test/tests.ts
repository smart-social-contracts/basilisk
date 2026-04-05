import { Test } from '../../../_test_lib';

export function getTests(qsCanister: any): Test[] {
    return [
        {
            name: 'sort empty',
            test: async () => {
                const result = await qsCanister.sort([]);
                return { Ok: result.length === 0 };
            }
        },
        {
            name: 'sort single',
            test: async () => {
                const result = await qsCanister.sort([1n]);
                return { Ok: result.length === 1 && result[0] === 1n };
            }
        },
        {
            name: 'sort multiple',
            test: async () => {
                const result = await qsCanister.sort([5n, 3n, 1n, 4n, 2n]);
                return {
                    Ok:
                        result.length === 5 &&
                        result[0] === 1n &&
                        result[1] === 2n &&
                        result[2] === 3n &&
                        result[3] === 4n &&
                        result[4] === 5n
                };
            }
        }
    ];
}
