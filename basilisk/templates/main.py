from basilisk import query, update, text, nat64, ic


# ---------------------------------------------------------------------------
# Starter example: a simple counter
# ---------------------------------------------------------------------------

counter = 0

@query
def greet(name: text) -> text:
    """Return a greeting message."""
    return f"Hello, {name}! The counter is at {counter}."

@query
def get_counter() -> nat64:
    """Read the current counter value."""
    return counter

@update
def increment() -> nat64:
    """Increment the counter and return the new value."""
    global counter
    counter += 1
    return counter


# ---------------------------------------------------------------------------
# Utility endpoints
# ---------------------------------------------------------------------------

@query
def status() -> str:
    """Health check endpoint."""
    return "ok"

@query
def get_time() -> nat64:
    """Return the current IC timestamp in nanoseconds."""
    return ic.time()

@query
def whoami() -> text:
    """Return the caller's principal ID."""
    return str(ic.caller())
