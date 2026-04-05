import { Test } from '../../_test_lib';

export function getTests(ctCanister: any): Test[] {
    return [
        {
            name: 'create_user',
            test: async () => {
                const result = await ctCanister.create_user('testuser');
                return { Ok: 'Ok' in result };
            }
        },
        {
            name: 'get_all_users',
            test: async () => {
                const result = await ctCanister.get_all_users();
                return { Ok: Array.isArray(result) };
            }
        }
    ];
}
