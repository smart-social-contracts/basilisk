import { Test } from '../../_test_lib';

export function getTests(kwCanister: any): Test[] {
    return [
        {
            name: 'simple_keyword',
            test: async () => {
                const input = { from_: 'hello' };
                const result = await kwCanister.simple_keyword(input);
                return { Ok: result.from_ === 'hello' };
            }
        },
        {
            name: 'rust_keyword',
            test: async () => {
                const result = await kwCanister.rust_keyword();
                return {
                    Ok:
                        result.abstract === false &&
                        result.become === 'Become' &&
                        result.fn === 'Function'
                };
            }
        },
        {
            name: 'rust_keyword_variant',
            test: async () => {
                const result = await kwCanister.rust_keyword_variant();
                return { Ok: 'type' in result };
            }
        },
        {
            name: 'keyword_variant',
            test: async () => {
                const input = { raise_: null };
                const result = await kwCanister.keyword_variant(input);
                return { Ok: 'raise_' in result };
            }
        },
        {
            name: 'complex_keyword',
            test: async () => {
                const result = await kwCanister.complex_keyword();
                return {
                    Ok:
                        result.False_ === false &&
                        result.True_ === 'False' &&
                        result.and_ === 1n &&
                        result.not_.from_ === 'False'
                };
            }
        }
    ];
}
