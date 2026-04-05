import { Test } from '../../_test_lib';

export function getTests(updateCanister: any): Test[] {
    return [
        {
            name: 'get_current_message initial',
            test: async () => {
                const result = await updateCanister.get_current_message();
                return { Ok: result === '' };
            }
        },
        {
            name: 'simple_update',
            test: async () => {
                await updateCanister.simple_update('hello');
                const result = await updateCanister.get_current_message();
                return { Ok: result === 'hello' };
            }
        },
        {
            name: 'simple_update overwrite',
            test: async () => {
                await updateCanister.simple_update('world');
                const result = await updateCanister.get_current_message();
                return { Ok: result === 'world' };
            }
        }
    ];
}
