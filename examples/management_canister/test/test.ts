import { createSnakeCaseProxy, getCanisterId, ok, runTests } from 'azle/test';
import { getTests } from 'azle/examples/management_canister/test/tests';
import { createActor } from './dfx_generated/management_canister';

const managementCanister = createActor(getCanisterId('management_canister'), {
    agentOptions: {
        host: 'http://127.0.0.1:8000'
    }
});

runTests(
    getTests(createSnakeCaseProxy(managementCanister)).map((test) => {
        if (test.name === 'executeUpdateSettings') {
            return {
                name: 'executeUpdateSettings',
                test: async () => {
                    try {
                        const canisterId =
                            await managementCanister.get_created_canister_id();
                        console.log('diag: canisterId =', canisterId?.toText?.() ?? String(canisterId));

                        const updateResult =
                            await managementCanister.execute_update_settings(canisterId);
                        console.log('diag: updateResult =', JSON.stringify(updateResult, (_, v) => typeof v === 'bigint' ? v.toString() : v));

                        if (!ok(updateResult)) {
                            return { Err: 'update failed: ' + (updateResult.Err ?? 'unknown') };
                        }

                        const statusResult =
                            await managementCanister.get_canister_status({
                                canister_id: canisterId
                            });
                        console.log('diag: statusResult =', JSON.stringify(statusResult, (_, v) => typeof v === 'bigint' ? v.toString() : v));

                        if (!ok(statusResult)) {
                            return { Err: 'status failed: ' + (statusResult.Err ?? 'unknown') };
                        }

                        const s = statusResult.Ok.settings;
                        console.log('diag: settings =', JSON.stringify(s, (_, v) => typeof v === 'bigint' ? v.toString() : v));
                        console.log('diag: compute_allocation =', s.compute_allocation, 'type:', typeof s.compute_allocation);
                        console.log('diag: memory_allocation =', s.memory_allocation, 'type:', typeof s.memory_allocation);
                        console.log('diag: freezing_threshold =', s.freezing_threshold, 'type:', typeof s.freezing_threshold);

                        return {
                            Ok:
                                s.compute_allocation === 1n &&
                                s.memory_allocation === 3_000_000n &&
                                s.freezing_threshold === 2_000_000n
                        };
                    } catch (e: any) {
                        console.log('diag: exception =', e?.message ?? String(e));
                        return { Err: e?.message ?? String(e) };
                    }
                }
            };
        }

        if (test.name === 'getCanisterStatus') {
            return {
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
                            canisterStatus.memory_size === 366n &&
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
            };
        }

        if (test.name === 'executeDepositCycles') {
            return {
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
            };
        }

        return test;
    })
);
