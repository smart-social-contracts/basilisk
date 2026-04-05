import { Test } from '../../_test_lib';

export function getTests(canister1: any, canister2: any): Test[] {
    return [
        {
            name: 'send_notification',
            test: async () => {
                const result = await canister1.send_notification();
                return { Ok: result !== undefined };
            }
        },
        {
            name: 'wait for notification processing',
            wait: 5_000
        },
        {
            name: 'canister2 get_notification_received',
            test: async () => {
                const result = await canister2.get_notification_received();
                return { Ok: result === true };
            }
        }
    ];
}
