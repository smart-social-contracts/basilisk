import { Test } from '../../_test_lib';

export function getTests(timersCanister: any): Test[] {
    return [
        {
            name: 'set_timers',
            test: async () => {
                const result = await timersCanister.set_timers(
                    1_000_000_000n,
                    2_000_000_000n
                );
                return {
                    Ok:
                        result.single !== undefined &&
                        result.inline !== undefined &&
                        result.capture !== undefined &&
                        result.repeat !== undefined
                };
            }
        },
        {
            name: 'wait for timers',
            wait: 5_000
        },
        {
            name: 'status_report',
            test: async () => {
                const result = await timersCanister.status_report();
                return {
                    Ok:
                        result.single === true &&
                        result.inline === 1 &&
                        result.capture === '🚩'
                };
            }
        }
    ];
}
