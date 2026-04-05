import { Test, ok } from '../../_test_lib';

export function getTests(managementCanister: any): Test[] {
    return [
        {
            name: 'executeCreateCanister',
            test: async () => {
                const result = await managementCanister.execute_create_canister();
                return { Ok: ok(result) };
            }
        },
        {
            name: 'getCanisterStatus',
            test: async () => {
                const canisterId =
                    await managementCanister.get_created_canister_id();

                const getCanisterStatusResult =
                    await managementCanister.get_canister_status({
                        canister_id: canisterId
                    });

                if (!ok(getCanisterStatusResult)) {
                    return {
                        Err: getCanisterStatusResult.Err
                    };
                }

                const canisterStatus = getCanisterStatusResult.Ok;

                return {
                    Ok:
                        'running' in canisterStatus.status &&
                        canisterStatus.memory_size > 0n &&
                        canisterStatus.cycles >= 800_000_000_000n &&
                        canisterStatus.settings.freezing_threshold ===
                            2_000_000n &&
                        canisterStatus.settings.controllers.length === 1 &&
                        canisterStatus.settings.memory_allocation ===
                            3_000_000n &&
                        canisterStatus.settings.compute_allocation === 1n &&
                        canisterStatus.module_hash.length === 0
                };
            }
        },
        {
            name: 'executeUpdateSettings',
            test: async () => {
                const result = await managementCanister.execute_update_settings();
                return { Ok: ok(result) };
            }
        },
        {
            name: 'executeInstallCode',
            test: async () => {
                const result = await managementCanister.execute_install_code();
                return { Ok: ok(result) };
            }
        },
        {
            name: 'executeUninstallCode',
            test: async () => {
                const result = await managementCanister.execute_uninstall_code();
                return { Ok: ok(result) };
            }
        },
        {
            name: 'executeDepositCycles',
            test: async () => {
                const canisterId =
                    await managementCanister.get_created_canister_id();

                const statusBeforeResult =
                    await managementCanister.get_canister_status({
                        canister_id: canisterId
                    });

                if (!ok(statusBeforeResult)) {
                    return {
                        Err: statusBeforeResult.Err
                    };
                }

                const statusBefore = statusBeforeResult.Ok;
                const cyclesBefore = statusBefore.cycles;

                const depositCyclesResult =
                    await managementCanister.execute_deposit_cycles(
                        canisterId
                    );

                if (!ok(depositCyclesResult)) {
                    return {
                        Err: depositCyclesResult.Err
                    };
                }

                const statusAfterResult =
                    await managementCanister.get_canister_status({
                        canister_id: canisterId
                    });

                if (!ok(statusAfterResult)) {
                    return {
                        Err: statusAfterResult.Err
                    };
                }

                const statusAfter = statusAfterResult.Ok;
                const cyclesAfter = statusAfter.cycles;

                return {
                    Ok: cyclesAfter > cyclesBefore
                };
            }
        },
        {
            name: 'getRawRand',
            test: async () => {
                const result = await managementCanister.get_raw_rand();
                return { Ok: ok(result) && result.Ok.length === 32 };
            }
        },
        {
            name: 'executeStopCanister',
            test: async () => {
                const result = await managementCanister.execute_stop_canister();
                return { Ok: ok(result) };
            }
        },
        {
            name: 'executeStartCanister',
            test: async () => {
                const result = await managementCanister.execute_start_canister();
                return { Ok: ok(result) };
            }
        },
        {
            name: 'executeDeleteCanister',
            test: async () => {
                const result = await managementCanister.execute_delete_canister();
                return { Ok: ok(result) };
            }
        }
    ];
}
