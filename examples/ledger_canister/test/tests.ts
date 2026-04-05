import { Test } from '../../_test_lib';

export function getTests(ledgerCanister: any): Test[] {
    return [
        {
            name: 'get_account_balance',
            test: async () => {
                const result = await ledgerCanister.get_account_balance();
                return { Ok: result !== undefined };
            }
        }
    ];
}
