import { Test } from '../../../_test_lib';

export function getTests(tecdsaCanister: any): Test[] {
    return [
        {
            name: 'public_key',
            test: async () => {
                const result = await tecdsaCanister.public_key();
                return {
                    Ok:
                        result.public_key_hex !== undefined &&
                        typeof result.public_key_hex === 'string' &&
                        result.public_key_hex.length > 0
                };
            }
        },
        {
            name: 'sign',
            test: async () => {
                const result = await tecdsaCanister.sign('hello');
                return {
                    Ok:
                        result.signature_hex !== undefined &&
                        typeof result.signature_hex === 'string' &&
                        result.signature_hex.length > 0
                };
            }
        }
    ];
}
