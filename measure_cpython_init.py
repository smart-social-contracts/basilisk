"""
Measure CPython WASM init instruction count using wasmtime fuel metering.

Stubs out all IC system API imports (ic0::*) so wasmtime can load the
canister wasm, then measures fuel consumed by canister_init.
"""
import wasmtime
import sys
import os

WASM_PATH = "/home/user/.config/basilisk/rust/target/wasm32-wasip1/release/update.wasm"


def stub_ic_imports(linker, module, store):
    """Define stub functions for all ic0::* imports."""
    for imp in module.imports:
        mod_name = imp.module
        field_name = imp.name
        ty = imp.type

        # Skip WASI imports (handled by linker.define_wasi)
        if mod_name.startswith("wasi_"):
            continue

        if isinstance(ty, wasmtime.FuncType):
            params = list(ty.params)
            results = list(ty.results)

            # Create a stub that returns 0 for each result
            def make_stub(p_count, r_types, name):
                def stub(*args):
                    ret = []
                    for r in r_types:
                        if r == wasmtime.ValType.i32():
                            ret.append(0)
                        elif r == wasmtime.ValType.i64():
                            ret.append(0)
                        elif r == wasmtime.ValType.f32():
                            ret.append(0.0)
                        elif r == wasmtime.ValType.f64():
                            ret.append(0.0)
                        else:
                            ret.append(0)
                    if len(ret) == 0:
                        return None
                    elif len(ret) == 1:
                        return ret[0]
                    return tuple(ret)
                return stub

            stub_fn = make_stub(len(params), results, f"{mod_name}::{field_name}")
            linker.define_func(mod_name, field_name, ty, stub_fn)


def measure(wasm_path: str, fuel: int, call_init: bool = False):
    """Measure fuel for instantiation and optionally canister_init."""
    config = wasmtime.Config()
    config.consume_fuel = True
    engine = wasmtime.Engine(config)
    store = wasmtime.Store(engine)
    store.set_fuel(fuel)

    wasi_config = wasmtime.WasiConfig()
    wasi_config.inherit_stdout()
    wasi_config.inherit_stderr()
    store.set_wasi(wasi_config)

    module = wasmtime.Module.from_file(engine, wasm_path)

    linker = wasmtime.Linker(engine)
    linker.define_wasi()
    stub_ic_imports(linker, module, store)

    fuel_before = store.get_fuel()
    try:
        instance = linker.instantiate(store, module)
    except Exception as e:
        consumed = fuel_before - store.get_fuel()
        return {"phase": "instantiate", "status": "trapped", "error": str(e)[:300], "fuel": consumed}

    inst_fuel = fuel_before - store.get_fuel()
    result = {"phase": "instantiate", "status": "ok", "fuel": inst_fuel}

    if call_init:
        # Find and call canister_init
        init_fn = instance.exports(store).get("canister_init")
        if init_fn is None:
            result["init"] = "no canister_init export found"
            return result

        fuel_before_init = store.get_fuel()
        try:
            init_fn(store)
        except Exception as e:
            consumed = fuel_before_init - store.get_fuel()
            result["init_status"] = "trapped"
            result["init_error"] = str(e)[:300]
            result["init_fuel"] = consumed
            return result

        init_consumed = fuel_before_init - store.get_fuel()
        result["init_status"] = "ok"
        result["init_fuel"] = init_consumed

    return result


if __name__ == "__main__":
    wasm_path = sys.argv[1] if len(sys.argv) > 1 else WASM_PATH
    print(f"WASM: {wasm_path}")
    print(f"Size: {os.path.getsize(wasm_path) / 1024 / 1024:.1f} MB")

    # Phase 1: Measure instantiation only (wasm startup, __wasm_call_ctors)
    print("\n=== Phase 1: WASM Instantiation ===")
    fuel = 100_000_000_000  # 100B
    r = measure(wasm_path, fuel, call_init=False)
    print(f"  Status: {r['status']}")
    if r['status'] == 'ok':
        print(f"  Fuel consumed: {r['fuel']:,}")
    else:
        print(f"  Error: {r.get('error', '')}")
        print(f"  Fuel consumed before trap: {r['fuel']:,}")

    # Phase 2: Measure instantiation + canister_init (CPython init happens here)
    print("\n=== Phase 2: Instantiation + canister_init ===")
    for fuel in [10_000_000_000, 100_000_000_000, 1_000_000_000_000, 10_000_000_000_000]:
        r = measure(wasm_path, fuel, call_init=True)
        inst = r['fuel']
        init_status = r.get('init_status', 'n/a')
        init_fuel = r.get('init_fuel', 0)
        total = inst + init_fuel

        label = f"fuel={fuel:>16,}"
        if init_status == 'ok':
            print(f"  {label}: OK! instantiate={inst:,} init={init_fuel:,} total={total:,}")
            break
        elif init_status == 'trapped':
            err_short = r.get('init_error', '')[:80]
            print(f"  {label}: TRAPPED at init (consumed {init_fuel:,}) - {err_short}")
        else:
            print(f"  {label}: {init_status}")

    # Summary
    print("\n=== Summary ===")
    if init_status == 'ok':
        print(f"  WASM instantiation: {inst:>20,} fuel")
        print(f"  canister_init:      {init_fuel:>20,} fuel")
        print(f"  TOTAL:              {total:>20,} fuel")
        print()
        for name, limit in [("query/init (5B)", 5_000_000_000), ("update (20B)", 20_000_000_000), ("DTS install (300B)", 300_000_000_000)]:
            if total <= limit:
                print(f"  ✅ Fits in {name}")
            else:
                print(f"  ❌ Exceeds {name} by {total/limit:.1f}x")
    else:
        print(f"  canister_init did not complete even with {fuel:,} fuel")
        print(f"  Last error: {r.get('init_error', '')[:200]}")
