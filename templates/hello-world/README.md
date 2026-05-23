# {{project-name}}

A Python canister for the Internet Computer, built with [Basilisk](https://github.com/smart-social-contracts/basilisk).

## Prerequisites

- [icp-cli](https://github.com/dfinity/icp-cli)
- Python 3.10+
- `pip install ic-basilisk`

## Deploy

```bash
icp network start -d
icp deploy
```

## Call

```bash
icp canister call {{project-name}} greet '("World")'
# ("Hello, World! The counter is at 0.")

icp canister call {{project-name}} increment
# (1)

icp canister call {{project-name}} get_counter
# (1)
```
