import { Test } from '../../_test_lib';

export function getTests(icApiCanister: any): Test[] {
    return [
        {
            name: 'caller',
            test: async () => {
                const result = await icApiCanister.caller();
                return { Ok: result !== undefined && result.toText() !== '' };
            }
        },
        {
            name: 'id',
            test: async () => {
                const result = await icApiCanister.id();
                return { Ok: result !== undefined && result.toText() !== '' };
            }
        },
        {
            name: 'time',
            test: async () => {
                const result = await icApiCanister.time();
                return { Ok: result > 0n };
            }
        },
        {
            name: 'canister_balance',
            test: async () => {
                const result = await icApiCanister.canister_balance();
                return { Ok: result > 0n };
            }
        },
        {
            name: 'canister_balance128',
            test: async () => {
                const result = await icApiCanister.canister_balance128();
                return { Ok: result > 0n };
            }
        },
        {
            name: 'trap',
            test: async () => {
                try {
                    const result = await icApiCanister.trap(
                        'here is the message'
                    );
                    return {
                        Ok: result
                    };
                } catch (error: any) {
                    return {
                        Ok: error.props.Message.includes('here is the message')
                    };
                }
            }
        }
    ];
}
