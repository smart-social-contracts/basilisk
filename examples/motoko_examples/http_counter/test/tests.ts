import { Test } from '../../../_test_lib';

export function getTests(): Test[] {
    return [
        {
            name: 'http_counter GET',
            test: async () => {
                const response = await fetch('http://127.0.0.1:8000/?canisterId=http_counter');
                return { Ok: response.status === 200 };
            }
        }
    ];
}
