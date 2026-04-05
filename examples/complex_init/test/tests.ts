import { Test } from '../../_test_lib';

export function getTests(ciCanister: any): Test[] {
    return [
        {
            name: 'greet_user',
            test: async () => {
                const result = await ciCanister.greet_user();
                return { Ok: typeof result === 'string' && result.length > 0 };
            }
        }
    ];
}
