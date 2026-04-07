import { Test } from '../../_test_lib';

export function getTests(ethCanister: any): Test[] {
    return [
        {
            name: 'eth_get_balance',
            test: async () => {
                const result = await ethCanister.eth_get_balance(
                    '0x0000000000000000000000000000000000000000'
                );
                return { Ok: result !== undefined };
            }
        },
        {
            name: 'eth_get_block_by_number',
            test: async () => {
                const result = await ethCanister.eth_get_block_by_number(0);
                return { Ok: result !== undefined };
            }
        }
    ];
}
