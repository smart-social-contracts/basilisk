import { Test } from '../../_test_lib';

export function getTests(guardCanister: any): Test[] {
    return [
        {
            name: 'loosely_guarded',
            test: async () => {
                const result = await guardCanister.loosely_guarded();
                return { Ok: result === true };
            }
        },
        {
            name: 'customErrorGuarded',
            test: async () => {
                try {
                    await guardCanister.custom_error_guarded();
                    return {
                        Err: 'Expected customErrorGuarded function to throw'
                    };
                } catch (error: any) {
                    return {
                        Ok: error.message.includes(
                            `Execution halted by \"throw custom error\" guard function`
                        )
                    };
                }
            }
        },
        {
            name: 'errorStringGuarded',
            test: async () => {
                try {
                    await guardCanister.error_string_guarded();
                    return {
                        Err: 'Expected errorStringGuarded function to throw'
                    };
                } catch (error: any) {
                    return {
                        Ok: error.message.includes(
                            `Execution halted by \"throw string\" guard function`
                        )
                    };
                }
            }
        },
        {
            name: 'tightlyGuarded',
            test: async () => {
                try {
                    await guardCanister.tightly_guarded();
                    return {
                        Err: 'Expected tightlyGuarded function to throw'
                    };
                } catch (error: any) {
                    return {
                        Ok: error.message.includes(
                            `Execution halted by \"unpassable\" guard function`
                        )
                    };
                }
            }
        },
        {
            name: 'modifyStateGuarded',
            test: async () => {
                const counterBefore = (await guardCanister.get_state())
                    .counter;
                const methodExecuted =
                    await guardCanister.modify_state_guarded();
                const counterAfter = (await guardCanister.get_state())
                    .counter;

                return {
                    Ok: counterBefore === 0 && methodExecuted && counterAfter === 1
                };
            }
        },
        {
            name: 'invalid_return_type_guarded',
            test: async () => {
                try {
                    await guardCanister.invalid_return_type_guarded();
                    return {
                        Err: 'invalid_return_type_guarded should have had an error'
                    };
                } catch (err: any) {
                    return {
                        Ok: err.message.includes(
                            'TypeError: expected Result but received str'
                        )
                    };
                }
            }
        },
        {
            name: 'bad_object_guarded',
            test: async () => {
                try {
                    await guardCanister.bad_object_guarded();
                    return { Err: 'bad_object_guarded should have had an error' };
                } catch (err: any) {
                    return {
                        Ok: err.message.includes(
                            'TypeError: expected Result but received dict'
                        )
                    };
                }
            }
        },
        {
            name: 'non_null_ok_value_guarded',
            test: async () => {
                try {
                    await guardCanister.non_null_ok_value_guarded();
                    return {
                        Err: 'non_null_ok_value_guarded should have had an error'
                    };
                } catch (err: any) {
                    return {
                        Ok: err.message.includes(
                            'TypeError: expected NoneType but received str'
                        )
                    };
                }
            }
        },
        {
            name: 'non_string_err_value_guarded',
            test: async () => {
                try {
                    await guardCanister.non_string_err_value_guarded();
                    return {
                        Err: 'non_string_err_value_guarded should have had an error'
                    };
                } catch (err: any) {
                    return {
                        Ok: err.message.includes(
                            "TypeError: Expected type 'str' but 'dict' found"
                        )
                    };
                }
            }
        },
        {
            name: 'name_error_guarded',
            test: async () => {
                try {
                    await guardCanister.name_error_guarded();
                    return {
                        Err: 'name_error_guarded should have had an error'
                    };
                } catch (err: any) {
                    return {
                        Ok: err.message.includes(
                            "NameError: name 'Ok' is not defined"
                        )
                    };
                }
            }
        }
    ];
}
