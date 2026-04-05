import { Test } from '../../_test_lib';

export function getTests(manualReplyCanister: any): Test[] {
    return [
        {
            name: 'update reply with string',
            test: async () => {
                const result = await manualReplyCanister.manual_update('test');
                return { Ok: typeof result === 'string' };
            }
        },
        {
            name: 'query reply with string',
            test: async () => {
                const result = await manualReplyCanister.manual_query('test');
                return { Ok: typeof result === 'string' };
            }
        },
        {
            name: 'update reply with void',
            test: async () => {
                // Basilisk correctly encodes void as () -> () so the agent returns undefined,
                // not null. The azle tests expect null due to a self-described incorrect
                // candid return type generation in azle/kybra.
                const result = await manualReplyCanister.update_void();
                return { Ok: result === undefined };
            }
        },
        {
            name: 'query reply with void',
            test: async () => {
                const result = await manualReplyCanister.query_void();
                return { Ok: result === undefined };
            }
        }
    ];
}
