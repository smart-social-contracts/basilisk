import { Test } from '../../_test_lib';

export function getTests(heartbeatAsyncCanister: any, heartbeatSyncCanister: any): Test[] {
    return [
        {
            name: 'wait for heartbeats',
            wait: 10_000
        },
        {
            name: 'heartbeat_async get_initialized',
            test: async () => {
                const result = await heartbeatAsyncCanister.get_initialized();
                return { Ok: result === true };
            }
        },
        {
            name: 'heartbeat_sync get_initialized',
            test: async () => {
                const result = await heartbeatSyncCanister.get_initialized();
                return { Ok: result === true };
            }
        }
    ];
}
