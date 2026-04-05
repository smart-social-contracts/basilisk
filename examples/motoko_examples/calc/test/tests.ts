import { Test } from '../../../_test_lib';

export function getTests(calcCanister: any): Test[] {
    return [
        {
            name: 'add',
            test: async () => {
                await calcCanister.clearall();
                const result = await calcCanister.add(5n);
                return { Ok: result === 5n };
            }
        },
        {
            name: 'sub',
            test: async () => {
                const result = await calcCanister.sub(2n);
                return { Ok: result === 3n };
            }
        },
        {
            name: 'mul',
            test: async () => {
                const result = await calcCanister.mul(4n);
                return { Ok: result === 12n };
            }
        },
        {
            name: 'div',
            test: async () => {
                const result = await calcCanister.div(3n);
                return { Ok: result.length === 1 && result[0] === 4n };
            }
        },
        {
            name: 'div by zero',
            test: async () => {
                const result = await calcCanister.div(0n);
                return { Ok: result.length === 0 };
            }
        },
        {
            name: 'clearall',
            test: async () => {
                await calcCanister.clearall();
                const result = await calcCanister.add(0n);
                return { Ok: result === 0n };
            }
        }
    ];
}
