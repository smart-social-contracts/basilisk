import { Test } from '../../../_test_lib';

export function getTests(counterCanister: any): Test[] {
    return [
        {
            name: 'get initial',
            test: async () => {
                const result = await counterCanister.get();
                return { Ok: result === 0n };
            }
        },
        {
            name: 'inc',
            test: async () => {
                await counterCanister.inc();
                const result = await counterCanister.get();
                return { Ok: result === 1n };
            }
        },
        {
            name: 'set',
            test: async () => {
                await counterCanister.set(42n);
                const result = await counterCanister.get();
                return { Ok: result === 42n };
            }
        },
        {
            name: 'inc after set',
            test: async () => {
                await counterCanister.inc();
                const result = await counterCanister.get();
                return { Ok: result === 43n };
            }
        }
    ];
}
