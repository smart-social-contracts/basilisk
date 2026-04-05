import { Test } from '../../../_test_lib';

export function getTests(factorialCanister: any): Test[] {
    return [
        {
            name: 'fac(0)',
            test: async () => {
                const result = await factorialCanister.fac(0n);
                return { Ok: result === 1n };
            }
        },
        {
            name: 'fac(1)',
            test: async () => {
                const result = await factorialCanister.fac(1n);
                return { Ok: result === 1n };
            }
        },
        {
            name: 'fac(5)',
            test: async () => {
                const result = await factorialCanister.fac(5n);
                return { Ok: result === 120n };
            }
        },
        {
            name: 'fac(10)',
            test: async () => {
                const result = await factorialCanister.fac(10n);
                return { Ok: result === 3_628_800n };
            }
        }
    ];
}
