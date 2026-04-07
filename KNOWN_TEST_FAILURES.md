# Known Test Failures

Examples excluded from CI due to known issues. Do **not** re-add to the CI matrix without fixing the underlying problem.

Last triaged: 2026-03-21

## Candid Type Limitations

| Example | Issue |
|---|---|
| `cross_canister_calls` | Cross-canister Record type resolves as text in variant |
| `func_types` | Func type (Principal, method) not serializable to Candid |
| `candid_encoding` | Func type encoding not supported |

## Feature Limitations

| Example | Issue |
|---|---|
| `motoko_tests/fixtures/http_counter` | Uses Func callback types + StableBTreeMap |
| `pre_and_post_upgrade` | StableBTreeMap upgrade persistence not implemented |

## External Dependencies / Environment

| Example | Issue |
|---|---|
| `bitcoin` | Needs bitcoin integration canister (tar extraction fails in CI) |
| `ethereum_json_rpc` | Needs `ETHEREUM_URL` secret |
| `ledger_canister` | ICP ledger canister Candid deserialization mismatch |

## PocketIC Limitations

| Example | Issue |
|---|---|
| `motoko_tests/fixtures/threshold_ecdsa` | Needs threshold ECDSA subnet |
| `composite_queries` | Composite query times out in PocketIC |
