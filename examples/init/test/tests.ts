import { Test } from '../../_test_lib';
import { Principal } from '@dfinity/principal';

export function getTests(initCanister: any): Test[] {
    return [
        {
            name: 'get_user',
            test: async () => {
                const result = await initCanister.get_user();
                return {
                    Ok: result.length === 1 && result[0].id === '0'
                };
            }
        },
        {
            name: 'get_reaction',
            test: async () => {
                const result = await initCanister.get_reaction();
                return {
                    Ok: result.length === 1 && 'Fire' in result[0]
                };
            }
        },
        {
            name: 'get_owner',
            test: async () => {
                const result = await initCanister.get_owner();
                return {
                    Ok: result.length === 1 && result[0] instanceof Principal
                };
            }
        }
    ];
}
