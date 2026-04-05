import { Test } from '../../../_test_lib';

export function getTests(psCanister: any): Test[] {
    return [
        {
            name: 'reset',
            test: async () => {
                const result = await psCanister.reset();
                return { Ok: result === 0n };
            }
        },
        {
            name: 'get initial',
            test: async () => {
                const result = await psCanister.get();
                return { Ok: result === 0n };
            }
        },
        {
            name: 'increment',
            test: async () => {
                const result = await psCanister.increment();
                return { Ok: result === 1n };
            }
        },
        {
            name: 'increment again',
            test: async () => {
                const result = await psCanister.increment();
                return { Ok: result === 2n };
            }
        },
        {
            name: 'get after increments',
            test: async () => {
                const result = await psCanister.get();
                return { Ok: result === 2n };
            }
        }
    ];
}
