import { Test } from '../../../_test_lib';

export function getTests(echoCanister: any): Test[] {
    return [
        {
            name: 'say',
            test: async () => {
                const result = await echoCanister.say('Hello!');
                return { Ok: result === 'Hello!' };
            }
        },
        {
            name: 'say empty',
            test: async () => {
                const result = await echoCanister.say('');
                return { Ok: result === '' };
            }
        }
    ];
}
