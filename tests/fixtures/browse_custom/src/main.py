from basilisk import query, update, text, nat, StableBTreeMap, GuardResult, ic

__basilisk_features__ = ["shell", "browse"]

scores = StableBTreeMap[text, nat](memory_id=0, max_key_size=64, max_value_size=128)


def admin_guard() -> GuardResult:
    if ic.is_controller(ic.caller()):
        return {"Ok": None}
    return {"Err": "admin only"}


@update(guard=admin_guard)
def __shell__(code: str) -> str:
    """Custom shell with admin guard and extra namespace."""
    import io
    import sys
    import traceback

    stdout, stderr = io.StringIO(), io.StringIO()
    sys.stdout, sys.stderr = stdout, stderr
    ns = {"__builtins__": __builtins__, "ic": ic, "scores": scores}
    try:
        exec(code, ns, ns)
    except Exception:
        traceback.print_exc()
    sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
    return stdout.getvalue() + stderr.getvalue()


@query
def __browse__(query: str) -> str:
    """Custom browse that only exposes scores with a custom label."""
    import json
    try:
        q = json.loads(query)
    except Exception:
        return json.dumps({"error": "invalid JSON"})
    action = q.get("action", "")

    if action == "schema":
        return json.dumps({"custom": True, "maps": ["scores"]})

    if action == "len":
        return json.dumps({"result": scores.len()})

    if action == "keys":
        return json.dumps({"result": scores.keys()})

    if action == "get":
        return json.dumps({"result": scores.get(q.get("key"))})

    return json.dumps({"error": f"unknown action: {action}"})


@update
def set_score(name: text, score: nat) -> text:
    scores.insert(name, score)
    return f"set {name}={score}"


@query
def get_score(name: text) -> nat:
    return scores.get(name) or 0
