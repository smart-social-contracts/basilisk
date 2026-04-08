# Contributing to Basilisk

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/smart-social-contracts/basilisk.git
cd basilisk
pip install -e ".[shell,test]"
```

## Running Tests

### Local integration tests (requires dfx)

```bash
# Install dfx: https://internetcomputer.org/docs/current/developer-docs/setup/install/
dfx start --clean --background

# Build all example WASMs (slow, ~minutes first time)
python scripts/build_all_wasms.py

# Run tests
BASILISK_PREBUILT_WASMS=1 pytest tests/integration/ -v
```

### IC mainnet tests (requires a deployed test canister)

```bash
BASILISK_TEST_CANISTER=<canister-id> \
BASILISK_TEST_NETWORK=ic \
PYTHONPATH=. pytest tests/test_tasks.py -v
```

See [tests/README.md](tests/README.md) for full details on the test suite architecture.

## Submitting Changes

1. Fork the repo and create a feature branch
2. Make your changes — keep PRs focused and small
3. Ensure tests pass (CI runs automatically on PRs)
4. Open a pull request against `main`

## Reporting Issues

Open an [issue](https://github.com/smart-social-contracts/basilisk/issues) with:
- What you expected vs what happened
- Steps to reproduce
- Basilisk version (`basilisk --version`)

## Code Style

- Follow the existing code style in each file
- Python code should work with Python 3.10+

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
