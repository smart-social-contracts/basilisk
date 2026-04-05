import { Test } from '../../_test_lib';

export function getTests(queryCanister: any): Test[] {
    return [
        {
            name: 'simple_query',
            test: async () => {
                const result = await queryCanister.simple_query();
                return { Ok: result === 'This is a query function' };
            }
        }
    ];
}
