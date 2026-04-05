import { Test } from '../../../_test_lib';

export function getTests(pbCanister: any): Test[] {
    return [
        {
            name: 'lookup empty',
            test: async () => {
                const result = await pbCanister.lookup('Alice');
                return { Ok: result.length === 0 };
            }
        },
        {
            name: 'insert',
            test: async () => {
                await pbCanister.insert('Alice', { desc: 'Friend', phone: '555-1234' });
                return { Ok: true };
            }
        },
        {
            name: 'lookup after insert',
            test: async () => {
                const result = await pbCanister.lookup('Alice');
                return {
                    Ok:
                        result.length === 1 &&
                        result[0].desc === 'Friend' &&
                        result[0].phone === '555-1234'
                };
            }
        }
    ];
}
