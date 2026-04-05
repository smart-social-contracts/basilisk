import { Test } from '../../_test_lib';

export function getTests(randomnessCanister: any): Test[] {
    return [
        {
            name: 'random_number',
            test: async () => {
                const result = await randomnessCanister.random_number();
                return { Ok: typeof result === 'number' && result >= 0 && result <= 1 };
            }
        },
        {
            name: 'random_number is different each call',
            test: async () => {
                const r1 = await randomnessCanister.random_number();
                const r2 = await randomnessCanister.random_number();
                return { Ok: r1 !== r2 };
            }
        }
    ];
}
