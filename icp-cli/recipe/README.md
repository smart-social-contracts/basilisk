# Basilisk Python Recipe

Build Python canisters for the Internet Computer using [Basilisk](https://github.com/smart-social-contracts/basilisk) and icp-cli.

## Usage

Reference this recipe in your `icp.yaml`.

### Remote (recommended)

Use the latest published recipe from GitHub releases:

```yaml
canisters:
  - name: my_canister
    recipe:
      type: "https://github.com/smart-social-contracts/basilisk/releases/latest/download/recipe.hbs"
      configuration:
        entry: src/main.py
        shrink: true
```

To pin a specific version:

```yaml
canisters:
  - name: my_canister
    recipe:
      type: "https://github.com/smart-social-contracts/basilisk/releases/download/v0.13.2/recipe.hbs"
      configuration:
        entry: src/main.py
        shrink: true
```

### Local development

Use a `file://` path while working from the Basilisk repo or a generated template:

```yaml
canisters:
  - name: my_canister
    recipe:
      type: file://../../recipe/recipe.hbs
      configuration:
        entry: src/main.py
        shrink: true
```

## Configuration Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| entry | string | No | Python entry point file | src/main.py |
| candid | string | No | Path to a custom Candid interface file. If omitted, Basilisk auto-generates a `.did` from decorators | — |
| shrink | boolean | No | Remove unused functions and debug info to reduce wasm size | false |
| compress | boolean | No | Gzip compress the output wasm | false |
| metadata | array | No | Array of `{name, value}` pairs for custom wasm metadata | [] |

## Prerequisites

- **Python 3.10+** (the recipe checks that `python3` is on your `PATH`)
- **ic-basilisk**: `pip install ic-basilisk`
- **ic-wasm** (included with icp-cli installation)
- **gzip** — only required if using `compress: true`

> **Note:** If you followed the [icp-cli installation guide](https://github.com/dfinity/icp-cli#installation), `ic-wasm` is already installed.

## Examples

### Minimal

```yaml
canisters:
  - name: backend
    recipe:
      type: "https://github.com/smart-social-contracts/basilisk/releases/latest/download/recipe.hbs"
      configuration:
        entry: src/main.py
```

### With candid, optimization, and metadata

```yaml
canisters:
  - name: backend
    recipe:
      type: "https://github.com/smart-social-contracts/basilisk/releases/latest/download/recipe.hbs"
      configuration:
        entry: src/main.py
        candid: backend.did
        shrink: true
        compress: true
        metadata:
          - name: "basilisk:version"
            value: "0.13.2"
```

## Build Process

When this recipe is executed:

1. Validates that `python3` and `ic-basilisk` are installed, plus `ic-wasm` and (optionally) `gzip`
2. Runs `python3 -m basilisk` which:
   - Downloads the pre-built CPython 3.13 WASM template (cached after first build)
   - Scans and bundles the user's Python source files
   - Generates a `.did` Candid interface from `@query`/`@update` decorators
   - Produces the final `.wasm` with injected Python code
3. Copies the wasm to `$ICP_WASM_OUTPUT_PATH`
4. Injects wasm metadata with `ic-wasm`:
   - Always sets `template:type` to `basilisk-python`
   - Sets `candid:service` from the `candid` file when that parameter is provided
   - Adds any custom metadata from the configuration
5. Optionally shrinks the wasm if `shrink: true`
6. Optionally gzip compresses the wasm if `compress: true`

## Project Structure

A typical Basilisk Python project:

```text
my-project/
├── src/
│   └── main.py          # Entry point
├── requirements.txt     # ic-basilisk dependency
└── icp.yaml             # Build configuration
```

## Python canister example

```python
from basilisk import query, update, text, nat64, ic

counter = 0

@query
def greet(name: text) -> text:
    return f"Hello, {name}! The counter is at {counter}."

@update
def increment() -> nat64:
    global counter
    counter += 1
    return counter

@query
def whoami() -> text:
    return str(ic.caller())
```

## Common Issues

### `ic-basilisk not found`

**Problem**: The recipe can't find the basilisk package.
**Solution**: Run `pip install ic-basilisk` (or add it to your `requirements.txt`).

### Build takes long on first run

**Problem**: First build downloads the CPython WASM template (~4 MB).
**Solution**: This is cached in `.basilisk/` after the first build. Subsequent builds are fast.

### WASM too large for IC deployment

**Problem**: The output wasm exceeds IC limits.
**Solution**: Enable `shrink: true` and `compress: true` in the recipe configuration.

## Related

- [Rust Recipe](https://github.com/dfinity/icp-cli-recipes/tree/main/recipes/rust) — For Rust canisters
- [Motoko Recipe](https://github.com/dfinity/icp-cli-recipes/tree/main/recipes/motoko) — For Motoko canisters
- [Pre-built Recipe](https://github.com/dfinity/icp-cli-recipes/tree/main/recipes/prebuilt) — For pre-compiled WASM files

Use this recipe when developing IC canisters in Python with Basilisk.
