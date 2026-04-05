import { Test } from '../../../_test_lib';

export function getTests(helloCanister: any): Test[] {
    return [
        {
            name: 'greet',
            test: async () => {
                const result = await helloCanister.greet('World');
                return { Ok: result === 'Hello, World!' };
            }
        },
        {
            name: 'greet empty',
            test: async () => {
                const result = await helloCanister.greet('');
                return { Ok: result === 'Hello, !' };
            }
        }
    ];
}
