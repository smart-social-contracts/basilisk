import { Test } from '../../_test_lib';

// TODO for now these tests need to be run on a fresh dfx start --clean, since cycles are not discarded on uninstall-code
export function getTests(cyclesCanister: any, intermediaryCanister: any): Test[] {
    return [
        {
            name: 'receive_cycles',
            test: async () => {
                const result = await intermediaryCanister.send_cycles();
                return { Ok: result !== undefined };
            }
        }
    ];
}
