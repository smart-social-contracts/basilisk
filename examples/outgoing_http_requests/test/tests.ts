import { Test } from '../../_test_lib';

export function getTests(ohrCanister: any): Test[] {
    return [
        {
            name: 'xkcd',
            test: async () => {
                const result = await ohrCanister.xkcd();
                return {
                    Ok:
                        result.status === 200 ||
                        result.status === 200n
                };
            }
        }
    ];
}
