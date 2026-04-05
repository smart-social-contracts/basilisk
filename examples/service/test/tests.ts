import { execSync } from 'child_process';
import { Test, getCanisterId } from '../../_test_lib';

// TODO Once this issue is resolved we can use actor-based tests: https://github.com/dfinity/agent-js/issues/702
// Until then we need to have the snake case names in the execSync calls
export function getTests(): Test[] {
    return [
        {
            name: 'serviceParam',
            test: async () => {
                const result = execSync(
                    `dfx canister call service service_param '(service "aaaaa-aa")'`
                )
                    .toString()
                    .trim();

                console.log(result);

                return {
                    Ok: result === '(service "aaaaa-aa")'
                };
            }
        },
        {
            name: 'serviceReturnType',
            test: async () => {
                const result = execSync(
                    `dfx canister call service service_return_type`
                )
                    .toString()
                    .trim();

                console.log(result);

                return {
                    Ok: result === '(service "ryjl3-tyaaa-aaaaa-aaaba-cai")'
                };
            }
        },
        {
            name: 'serviceList',
            test: async () => {
                const result = execSync(
                    `dfx canister call service service_list '(vec { service "r7inp-6aaaa-aaaaa-aaabq-cai"; service "rrkah-fqaaa-aaaaa-aaaaq-cai" })'`
                )
                    .toString()
                    .trim();

                console.log(result);

                return {
                    Ok:
                        result ===
                        `(
  vec {
    service "r7inp-6aaaa-aaaaa-aaabq-cai";
    service "rrkah-fqaaa-aaaaa-aaaaq-cai";
  },
)`
                };
            }
        },
        {
            name: 'serviceCrossCanisterCall',
            test: async () => {
                const result = execSync(
                    `dfx canister call service service_cross_canister_call '(service "${getCanisterId(
                        'some_service'
                    )}")'`
                )
                    .toString()
                    .trim();

                console.log(result);

                return {
                    Ok: result === '(variant { Ok = "SomeService update1" })'
                };
            }
        }
    ];
}
