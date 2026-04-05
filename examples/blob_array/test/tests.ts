import { Test } from '../../_test_lib';

export function getTests(blobCanister: any): Test[] {
    return [
        {
            name: 'get_blob',
            test: async () => {
                const result = await blobCanister.get_blob();
                const decoded = new TextDecoder().decode(result);
                return { Ok: decoded === 'hello' };
            }
        },
        {
            name: 'get_blobs',
            test: async () => {
                const result = await blobCanister.get_blobs();
                return {
                    Ok:
                        result.length === 2 &&
                        new TextDecoder().decode(result[0]) === 'hello' &&
                        new TextDecoder().decode(result[1]) === 'world'
                };
            }
        }
    ];
}
