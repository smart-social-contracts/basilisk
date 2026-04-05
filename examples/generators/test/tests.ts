import { Test } from '../../_test_lib';

export function getTests(generatorsCanister: any): Test[] {
    return [
        {
            name: 'get_randomness_directly',
            test: async () => {
                const result =
                    await generatorsCanister.get_randomness_directly();

                return {
                    Ok: result.length === 32
                };
            }
        },
        {
            name: 'get_randomness_indirectly',
            test: async () => {
                const result =
                    await generatorsCanister.get_randomness_indirectly();

                return {
                    Ok: result.length === 32
                };
            }
        },
        {
            name: 'get_randomness_super_indirectly',
            test: async () => {
                const result =
                    await generatorsCanister.get_randomness_super_indirectly();

                return {
                    Ok: result.length === 96
                };
            }
        }
    ];
}
