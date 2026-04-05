import { Test } from '../../_test_lib';

export function getTests(inspectMessageCanister: any): Test[] {
    return [
        {
            name: 'calling `ic.acceptMessage` in inspectMessage',
            test: async () => {
                const result = await inspectMessageCanister.accessible();
                return { Ok: result === true };
            }
        },
        {
            name: 'inaccessible',
            test: async () => {
                try {
                    await inspectMessageCanister.inaccessible();
                    return { Err: 'Expected inaccessible to throw' };
                } catch (error) {
                    return { Ok: true };
                }
            }
        }
        // TODO remove this once this is resolved: https://forum.dfinity.org/t/not-calling-accept-message-in-inspect-message-not-rejecting-immediately-in-dfx-0-14-2-beta-2/21105
        // 'not calling `ic.acceptMessage` in inspectMessage' and 'throwing in `inspectMessage`' are excluded
    ];
}
