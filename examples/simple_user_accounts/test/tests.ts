import { Test } from '../../_test_lib';

export function getTests(userCanister: any): Test[] {
    return [
        {
            name: 'get_all_users initially empty',
            test: async () => {
                const result = await userCanister.get_all_users();
                return { Ok: result.length === 0 };
            }
        },
        {
            name: 'create_user',
            test: async () => {
                const result = await userCanister.create_user('alice');
                return {
                    Ok: result.id === '0' && result.username === 'alice'
                };
            }
        },
        {
            name: 'get_user_by_id',
            test: async () => {
                const result = await userCanister.get_user_by_id('0');
                return {
                    Ok: result.length === 1 && result[0].username === 'alice'
                };
            }
        },
        {
            name: 'create second user',
            test: async () => {
                const result = await userCanister.create_user('bob');
                return {
                    Ok: result.id === '1' && result.username === 'bob'
                };
            }
        },
        {
            name: 'get_all_users returns both',
            test: async () => {
                const result = await userCanister.get_all_users();
                return { Ok: result.length === 2 };
            }
        },
        {
            name: 'get non-existent user',
            test: async () => {
                const result = await userCanister.get_user_by_id('999');
                return { Ok: result.length === 0 };
            }
        }
    ];
}
