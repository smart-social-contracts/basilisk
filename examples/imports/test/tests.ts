import { Test } from '../../_test_lib';

export function getTests(importsCanister: any): Test[] {
    return [
        {
            name: 'get_one',
            test: async () => {
                const result = await importsCanister.get_one();
                return { Ok: typeof result === 'string' && result.length > 0 };
            }
        },
        {
            name: 'get_two',
            test: async () => {
                const result = await importsCanister.get_two();
                return { Ok: typeof result === 'string' && result.length > 0 };
            }
        },
        {
            name: 'get_three',
            test: async () => {
                const result = await importsCanister.get_three();
                return { Ok: typeof result === 'string' && result.length > 0 };
            }
        },
        {
            name: 'sha224_hash',
            test: async () => {
                const result = await importsCanister.sha224_hash('hello');
                return { Ok: typeof result === 'string' && result.length === 56 };
            }
        },
        {
            name: 'get_math_message',
            test: async () => {
                const result = await importsCanister.get_math_message();
                return { Ok: result === 11n };
            }
        },
        {
            name: 'boltons_floor',
            test: async () => {
                const result = await importsCanister.boltons_floor(456.76);
                return { Ok: result === 456n };
            }
        }
    ];
}
