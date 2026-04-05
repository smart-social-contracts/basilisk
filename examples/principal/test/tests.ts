import { Test } from '../../_test_lib';
import { Principal } from '@dfinity/principal';

export function getTests(principalCanister: any): Test[] {
    return [
        {
            name: 'principal_return_type',
            test: async () => {
                const result = await principalCanister.principal_return_type();
                return {
                    Ok: result instanceof Principal && result.toString() === 'aaaaa-aa'
                };
            }
        },
        {
            name: 'principal_param',
            test: async () => {
                const p = Principal.fromText('aaaaa-aa');
                const result = await principalCanister.principal_param(p);
                return {
                    Ok: result instanceof Principal && result.toString() === 'aaaaa-aa'
                };
            }
        },
        {
            name: 'principal_in_record',
            test: async () => {
                const result = await principalCanister.principal_in_record();
                return {
                    Ok:
                        result.id instanceof Principal &&
                        result.id.toString() === 'aaaaa-aa' &&
                        result.username === 'lastmjs'
                };
            }
        },
        {
            name: 'principal_in_variant',
            test: async () => {
                const result = await principalCanister.principal_in_variant();
                return {
                    Ok: 'WaitingOn' in result && result.WaitingOn.toString() === 'aaaaa-aa'
                };
            }
        },
        {
            name: 'principal_from_text',
            test: async () => {
                const result = await principalCanister.principal_from_text('aaaaa-aa');
                return {
                    Ok: result instanceof Principal && result.toString() === 'aaaaa-aa'
                };
            }
        },
        {
            name: 'principal_to_text',
            test: async () => {
                const p = Principal.fromText('aaaaa-aa');
                const result = await principalCanister.principal_to_text(p);
                return { Ok: result === 'aaaaa-aa' };
            }
        },
        {
            name: 'principal_to_blob',
            test: async () => {
                const p = Principal.fromText('aaaaa-aa');
                const result = await principalCanister.principal_to_blob(p);
                return { Ok: result instanceof Uint8Array };
            }
        },
        {
            name: 'principal_from_blob',
            test: async () => {
                const p = Principal.fromText('aaaaa-aa');
                const blob = p.toUint8Array();
                const result = await principalCanister.principal_from_blob(blob);
                return {
                    Ok: result instanceof Principal && result.toString() === 'aaaaa-aa'
                };
            }
        }
    ];
}
