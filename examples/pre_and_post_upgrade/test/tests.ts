import { Test } from '../../_test_lib';

export function getTests(ppCanister: any): Test[] {
    return [
        {
            name: 'set_entry',
            test: async () => {
                await ppCanister.set_entry({ key: 'hello', value: 42n });
                const entries = await ppCanister.get_entries();
                return {
                    Ok: entries.some((e: any) => e.key === 'hello' && e.value === 42n)
                };
            }
        },
        {
            name: 'get_entries',
            test: async () => {
                const entries = await ppCanister.get_entries();
                return { Ok: Array.isArray(entries) && entries.length >= 1 };
            }
        }
    ];
}
