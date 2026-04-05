import { Test } from '../../_test_lib';
import { Principal } from '@dfinity/principal';

export function getTests(ptCanister: any): Test[] {
    return [
        {
            name: 'get_string',
            test: async () => {
                const result = await ptCanister.get_string();
                return { Ok: result === 'string' };
            }
        },
        {
            name: 'print_string',
            test: async () => {
                const result = await ptCanister.print_string('hello');
                return { Ok: result === 'hello' };
            }
        },
        {
            name: 'get_text',
            test: async () => {
                const result = await ptCanister.get_text();
                return { Ok: result === 'text' };
            }
        },
        {
            name: 'print_text',
            test: async () => {
                const result = await ptCanister.print_text('hello');
                return { Ok: result === 'hello' };
            }
        },
        {
            name: 'get_int',
            test: async () => {
                const result = await ptCanister.get_int();
                return { Ok: result === 170_141_183_460_469_231_731_687_303_715_884_105_727n };
            }
        },
        {
            name: 'print_int',
            test: async () => {
                const result = await ptCanister.print_int(42n);
                return { Ok: result === 42n };
            }
        },
        {
            name: 'get_int64',
            test: async () => {
                const result = await ptCanister.get_int64();
                return { Ok: result === 9_223_372_036_854_775_807n };
            }
        },
        {
            name: 'get_int32',
            test: async () => {
                const result = await ptCanister.get_int32();
                return { Ok: result === 2_147_483_647 };
            }
        },
        {
            name: 'get_int16',
            test: async () => {
                const result = await ptCanister.get_int16();
                return { Ok: result === 32_767 };
            }
        },
        {
            name: 'get_int8',
            test: async () => {
                const result = await ptCanister.get_int8();
                return { Ok: result === 127 };
            }
        },
        {
            name: 'get_nat',
            test: async () => {
                const result = await ptCanister.get_nat();
                return { Ok: result === 340_282_366_920_938_463_463_374_607_431_768_211_455n };
            }
        },
        {
            name: 'get_nat64',
            test: async () => {
                const result = await ptCanister.get_nat64();
                return { Ok: result === 18_446_744_073_709_551_615n };
            }
        },
        {
            name: 'get_nat32',
            test: async () => {
                const result = await ptCanister.get_nat32();
                return { Ok: result === 4_294_967_295 };
            }
        },
        {
            name: 'get_nat16',
            test: async () => {
                const result = await ptCanister.get_nat16();
                return { Ok: result === 65_535 };
            }
        },
        {
            name: 'get_nat8',
            test: async () => {
                const result = await ptCanister.get_nat8();
                return { Ok: result === 255 };
            }
        },
        {
            name: 'get_float64',
            test: async () => {
                const result = await ptCanister.get_float64();
                return { Ok: Math.abs(result - Math.E) < 0.0001 };
            }
        },
        {
            name: 'get_float32',
            test: async () => {
                const result = await ptCanister.get_float32();
                return { Ok: Math.abs(result - Math.PI) < 0.001 };
            }
        },
        {
            name: 'get_bool',
            test: async () => {
                const result = await ptCanister.get_bool();
                return { Ok: result === true };
            }
        },
        {
            name: 'print_bool',
            test: async () => {
                const result = await ptCanister.print_bool(false);
                return { Ok: result === false };
            }
        },
        {
            name: 'get_principal',
            test: async () => {
                const result = await ptCanister.get_principal();
                return {
                    Ok: result instanceof Principal &&
                        result.toString() === 'rrkah-fqaaa-aaaaa-aaaaq-cai'
                };
            }
        },
        {
            name: 'get_null',
            test: async () => {
                const result = await ptCanister.get_null();
                return { Ok: result === null };
            }
        },
        {
            name: 'get_reserved',
            test: async () => {
                const result = await ptCanister.get_reserved();
                return { Ok: result === null };
            }
        }
    ];
}
