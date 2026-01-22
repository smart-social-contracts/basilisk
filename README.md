# Basilisk

[![Test](https://github.com/smart-social-contracts/basilisk/actions/workflows/test.yml/badge.svg)](https://github.com/smart-social-contracts/basilisk/actions/workflows/test.yml)

A Python CDK for the [Internet Computer](https://internetcomputer.org/), forked from [Kybra](https://github.com/demergent-labs/kybra).

## Features

- Full Python support for IC canister development
- **Chunked code upload API** for canisters larger than 10MB (see `RENAME_STATUS.md`)

## Disclaimer

Basilisk may have unknown security vulnerabilities due to the following:

- Limited production deployments on the IC
- No extensive automated property tests
- No independent security reviews/audits
- Uses a Python interpreter less mature than CPython

## Documentation

Documentation is available in the `docs/` directory. For the original Kybra documentation, see [The Kybra Book](https://demergent-labs.github.io/kybra/).

## Installation

```bash
pip install basilisk
```

## Discussion

Feel free to open [issues](https://github.com/smart-social-contracts/basilisk/issues).

## License

See [LICENSE](LICENSE) and [NOTICE](NOTICE).
