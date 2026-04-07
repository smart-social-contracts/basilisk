import { Test, ok } from '../../_test_lib';

/**
 * Converts a hex string into an array of bytes
 */
function hex_string_to_bytes(hex: string): Uint8Array {
    return Uint8Array.from(
        hex.match(/.{1,2}/g)?.map((byte) => parseInt(byte, 16)) || []
    );
}

export interface BitcoinState {
    signedTxHex: string;
}

export interface BitcoinWallets {
    alice: { p2wpkh: string };
    bob: { p2wpkh: string };
}

export interface BitcoinCli {
    getReceivedByAddress: (address: string, minconf?: number) => number;
    generateToAddress: (blocks: number, address: string) => void;
}

export function getTests(
    bitcoinCanister: any,
    state: BitcoinState,
    wallets: BitcoinWallets,
    bitcoinCli: BitcoinCli
): Test[] {
    return [
        {
            name: 'wait for blockchain balance to reflect',
            wait: 60_000
        },
        {
            name: 'get_balance',
            test: async () => {
                const result = await bitcoinCanister.get_balance(
                    wallets.alice.p2wpkh
                );

                if (!ok(result)) {
                    return { Err: result.Err };
                }

                const block_reward = 5_000_000_000n;
                const blocks_mined_in_setup = 101n;
                const expected_balance = block_reward * blocks_mined_in_setup;

                return {
                    Ok: result.Ok === expected_balance
                };
            }
        },
        {
            name: 'get_utxos',
            test: async () => {
                const result = await bitcoinCanister.get_utxos(
                    wallets.alice.p2wpkh
                );

                if (!ok(result)) {
                    return { Err: result.Err };
                }

                return {
                    Ok:
                        result.Ok.tip_height === 101 &&
                        result.Ok.utxos.length === 101
                };
            }
        },
        {
            name: 'get_current_fee_percentiles',
            test: async () => {
                const result =
                    await bitcoinCanister.get_current_fee_percentiles();

                if (!ok(result)) {
                    return { Err: result.Err };
                }

                return {
                    Ok: result.Ok.length === 0 // TODO: This should have entries
                };
            }
        },
        {
            name: 'send transaction',
            test: async () => {
                const balance_before_transaction =
                    bitcoinCli.getReceivedByAddress(wallets.bob.p2wpkh);

                const tx_bytes = hex_string_to_bytes(state.signedTxHex);

                const result = await bitcoinCanister.send_transaction(tx_bytes);

                if (!ok(result)) {
                    return {
                        Err: result.Err
                    };
                }

                bitcoinCli.generateToAddress(1, wallets.alice.p2wpkh);

                // Wait for generated block to be pulled into replica
                await new Promise((resolve) => setTimeout(resolve, 5000));

                const balance_after_transaction =
                    bitcoinCli.getReceivedByAddress(wallets.bob.p2wpkh, 0);

                return {
                    Ok:
                        result.Ok === true &&
                        balance_before_transaction === 0 &&
                        balance_after_transaction === 1
                };
            }
        }
    ];
}
