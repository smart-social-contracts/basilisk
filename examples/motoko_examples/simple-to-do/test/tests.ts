import { Test } from '../../../_test_lib';

export function getTests(todoCanister: any): Test[] {
    return [
        {
            name: 'get_todos initially empty',
            test: async () => {
                const result = await todoCanister.get_todos();
                return { Ok: result.length === 0 };
            }
        },
        {
            name: 'add_todo',
            test: async () => {
                const id = await todoCanister.add_todo('Buy milk');
                return { Ok: id === 0n };
            }
        },
        {
            name: 'add_todo second',
            test: async () => {
                const id = await todoCanister.add_todo('Walk dog');
                return { Ok: id === 1n };
            }
        },
        {
            name: 'get_todos after adding',
            test: async () => {
                const result = await todoCanister.get_todos();
                return {
                    Ok:
                        result.length === 2 &&
                        result[0].description === 'Buy milk' &&
                        result[0].completed === false
                };
            }
        },
        {
            name: 'complete_todo',
            test: async () => {
                await todoCanister.complete_todo(0n);
                const result = await todoCanister.get_todos();
                return { Ok: result[0].completed === true };
            }
        },
        {
            name: 'show_todos',
            test: async () => {
                const result = await todoCanister.show_todos();
                return { Ok: typeof result === 'string' && result.includes('Buy milk') };
            }
        },
        {
            name: 'clear_completed',
            test: async () => {
                await todoCanister.clear_completed();
                const result = await todoCanister.get_todos();
                return { Ok: result.length === 1 && result[0].description === 'Walk dog' };
            }
        }
    ];
}
