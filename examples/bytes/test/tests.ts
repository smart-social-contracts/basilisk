import { Test } from '../../_test_lib';

export function getTests(bytesCanister: any): Test[] {
    return [
        {
            name: 'get_bytes roundtrip',
            test: async () => {
                const input = new Uint8Array([1, 2, 3, 4, 5]);
                const result = await bytesCanister.get_bytes(input);
                return {
                    Ok:
                        result instanceof Uint8Array &&
                        result.length === 5 &&
                        result[0] === 1 &&
                        result[4] === 5
                };
            }
        },
        {
            name: 'get_bytes empty',
            test: async () => {
                const input = new Uint8Array([]);
                const result = await bytesCanister.get_bytes(input);
                return { Ok: result instanceof Uint8Array && result.length === 0 };
            }
        }
    ];
}
