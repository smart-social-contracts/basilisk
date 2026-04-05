import { Test } from '../../_test_lib';

export function getTests(erc20Canister: any): Test[] {
    return [
        {
            name: 'initialize_supply',
            test: async () => {
                const result = await erc20Canister.initialize_supply(
                    'TestToken', 'addr1', 'TT', 1_000_000n
                );
                return { Ok: result === true };
            }
        },
        {
            name: 'name',
            test: async () => {
                const result = await erc20Canister.name();
                return { Ok: result === 'TestToken' };
            }
        },
        {
            name: 'ticker',
            test: async () => {
                const result = await erc20Canister.ticker();
                return { Ok: result === 'TT' };
            }
        },
        {
            name: 'total_supply',
            test: async () => {
                const result = await erc20Canister.total_supply();
                return { Ok: result === 1_000_000n };
            }
        },
        {
            name: 'balance of original address',
            test: async () => {
                const result = await erc20Canister.balance('addr1');
                return { Ok: result === 1_000_000n };
            }
        },
        {
            name: 'transfer',
            test: async () => {
                const result = await erc20Canister.transfer('addr1', 'addr2', 500n);
                return { Ok: result === true };
            }
        },
        {
            name: 'balance after transfer - sender',
            test: async () => {
                const result = await erc20Canister.balance('addr1');
                return { Ok: result === 999_500n };
            }
        },
        {
            name: 'balance after transfer - receiver',
            test: async () => {
                const result = await erc20Canister.balance('addr2');
                return { Ok: result === 500n };
            }
        }
    ];
}
