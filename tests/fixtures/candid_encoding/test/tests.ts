import { Test } from '../../_test_lib';

export function getTests(ceCanister: any): Test[] {
    return [
        {
            name: 'candid_encode and candid_decode roundtrip',
            test: async () => {
                const encoded = await ceCanister.candid_encode('(42 : nat)');
                const decoded = await ceCanister.candid_decode(encoded);
                return { Ok: decoded.includes('42') };
            }
        },
        {
            name: 'candid_encode text',
            test: async () => {
                const encoded = await ceCanister.candid_encode('("hello")');
                return { Ok: encoded instanceof Uint8Array && encoded.length > 0 };
            }
        },
        {
            name: 'candid_decode text',
            test: async () => {
                const encoded = await ceCanister.candid_encode('("hello")');
                const decoded = await ceCanister.candid_decode(encoded);
                return { Ok: decoded.includes('hello') };
            }
        }
    ];
}
