import { Test } from '../../_test_lib';

export function getTests(canister1: any, canister2: any): Test[] {
    return [
        {
            name: 'canister1 transfer',
            test: async () => {
                const result = await canister1.transfer('abc123');
                return { Ok: 'Ok' in result };
            }
        },
        {
            name: 'canister2 transfer',
            test: async () => {
                const result = await canister2.transfer('abc123');
                return { Ok: 'Ok' in result };
            }
        },
        {
            name: 'canister1 balance',
            test: async () => {
                const result = await canister1.balance('abc123');
                return { Ok: result !== undefined };
            }
        },
        {
            name: 'canister1 account',
            test: async () => {
                const result = await canister1.account({ address: 'abc123', balance: 0n });
                return { Ok: result !== undefined };
            }
        },
        {
            name: 'canister1 trap',
            test: async () => {
                const result = await canister1.trap();
                return {
                    Ok: 'Err' in result &&
                        result.Err.includes('Rejection code 5') &&
                        result.Err.includes('hahahaha')
                };
            }
        }
    ];
}
