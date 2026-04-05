import { Test } from '../../../_test_lib';

export function getTests(hwCanister: any): Test[] {
    return [
        {
            name: 'main',
            test: async () => {
                await hwCanister.main();
                return { Ok: true };
            }
        }
    ];
}
