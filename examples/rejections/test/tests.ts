import { Test } from '../../_test_lib';

export function getTests(rejectionsCanister: any): Test[] {
    return [
        {
            name: 'get_rejection_code_no_error',
            test: async () => {
                const result = await rejectionsCanister.get_rejection_code_no_error();
                return { Ok: result !== undefined };
            }
        },
        {
            name: 'get_rejection_message_no_error',
            test: async () => {
                const result = await rejectionsCanister.get_rejection_message_no_error();
                return { Ok: typeof result === 'string' };
            }
        }
    ];
}
