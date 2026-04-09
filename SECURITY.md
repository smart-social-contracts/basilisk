# Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability in Basilisk, **please report it responsibly**.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please email: **contact@smartsocialcontracts.org** using a secure channel like GPG.

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will acknowledge receipt within 48 hours and aim to provide a fix or mitigation within 7 days for critical issues.

## Supported Versions

| Version | Supported |
| ------- | --------- |
| Latest  | ✅        |
| < Latest | ❌       |

Only the latest release receives security updates. We recommend always using the latest version.

## Security Model

### What Basilisk Is

Basilisk compiles Python code into WebAssembly canisters that run on the Internet Computer (IC). It provides:

- A **build tool** that injects Python source into a pre-compiled Rust/WASM template
- A **runtime** (CPython interpreter embedded in WASM) that executes Python code on-chain
- **IC API bindings** for cross-canister calls, stable memory, timers, and cryptography
- A **shell** (`basilisk shell`) for interactive canister management

### Threat Model

**Trusted:**
- The canister controller(s) — they can execute arbitrary code via `execute_code_shell`
- The IC subnet nodes — they execute canister code in consensus

**Untrusted:**
- External callers — any principal on the IC can call your canister's public endpoints
- Inter-canister call responses — callees can return arbitrary data or never respond

**Out of scope:**
- IC subnet compromise (Byzantine fault tolerance is the IC's responsibility)
- Node operator memory inspection (canister memory on standard subnets is visible to node operators — do not store secrets in canister state)

### Key Security Properties

1. **Access control is the developer's responsibility.** Basilisk provides `guard_against_non_controllers` and `ic.is_controller()`, but developers must apply guards to their endpoints. Endpoints without guards are callable by anyone.

2. **`execute_code_shell` is an arbitrary code execution endpoint.** It MUST be guarded with `guard_against_non_controllers` or equivalent. The built-in test canister and templates apply this guard by default.

3. **Cross-canister calls are async and subject to interleaving.** Between `yield` points in async methods, other messages can execute and mutate state (TOCTOU). Implement per-caller locking for financial operations.

4. **`pre_upgrade` can trap if stable memory serialization exceeds instruction limits.** Monitor canister data size. Use the `StableBTreeMap` (memory_id=255) file persistence for large file storage instead of accumulating data in the legacy stable memory region.

5. **Query calls run on a single replica and can be spoofed.** Do not rely on query responses for security-critical decisions. Use update calls or certified variables for trustworthy reads.

## Security Checklist for Canister Developers

- [ ] Apply `guard_against_non_controllers` to all admin/sensitive endpoints
- [ ] Reject the anonymous principal (`2vxsx-fae`) in authentication-sensitive endpoints
- [ ] Add a backup controller to your canister (`dfx canister update-settings --add-controller`)
- [ ] Monitor cycles balance and set appropriate `freezing_threshold`
- [ ] Do not store secrets (API keys, private keys) in canister state
- [ ] Implement per-caller locking for async operations that mutate financial state
- [ ] Validate and bound user-controlled input sizes
- [ ] Never call `fetchRootKey()` in production frontend code
- [ ] Test guard enforcement with non-controller identities

## Known Limitations

1. **No Python sandbox within the canister.** Python code running inside the canister has full access to all IC APIs, stable memory, and the in-memory filesystem. Access control is enforced at the canister method boundary, not within Python execution.

2. **SSH server has no authentication in dev mode.** The `basilisk sshd` command accepts any connection by default. Only use it on `localhost` or trusted networks.

3. **Template WASM integrity.** The pre-built WASM template is downloaded from GitHub Releases over HTTPS. No additional checksum verification is currently performed.

4. **Canister memory is not encrypted.** On standard application subnets, node operators can inspect canister memory. Use vetKD for on-chain secret management if needed.
