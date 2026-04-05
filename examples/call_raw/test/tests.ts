import { Test, getCanisterId } from '../../_test_lib';

export function getTests(callRawCanister: any): Test[] {
    return [
        {
            name: 'execute_call_raw',
            test: async () => {
                const canisterId = getCanisterId('call_raw');
                const result = await callRawCanister.execute_call_raw(
                    canisterId,
                    'execute_call_raw',
                    `(principal "${canisterId}", "execute_call_raw", "()", 0 : nat64)`,
                    0n
                );
                return { Ok: 'Ok' in result };
            }
        },
        {
            name: 'execute_call_raw128',
            test: async () => {
                const canisterId = getCanisterId('call_raw');
                const result = await callRawCanister.execute_call_raw128(
                    canisterId,
                    'execute_call_raw128',
                    `(principal "${canisterId}", "execute_call_raw128", "()", 0 : nat)`,
                    0n
                );
                return { Ok: 'Ok' in result };
            }
        }
    ];
}
