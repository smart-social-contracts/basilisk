import { Test } from '../../_test_lib';

export function getTests(counterCanister: any): Test[] {
    return [
        {
            name: 'read_count initial value',
            test: async () => {
                const result = await counterCanister.read_count();
                return { Ok: result === 0n };
            }
        },
        {
            name: 'first increment_count',
            test: async () => {
                const result = await counterCanister.increment_count();
                return { Ok: result === 1n };
            }
        },
        {
            name: 'read_count after first increment',
            test: async () => {
                const result = await counterCanister.read_count();
                return { Ok: result === 1n };
            }
        },
        {
            name: 'second increment_count',
            test: async () => {
                const result = await counterCanister.increment_count();
                return { Ok: result === 2n };
            }
        },
        {
            name: 'read_count after second increment',
            test: async () => {
                const result = await counterCanister.read_count();
                return { Ok: result === 2n };
            }
        }
    ];
}
