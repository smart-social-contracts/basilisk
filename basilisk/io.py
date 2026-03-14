"""Basilisk I/O utilities for canister-side operations."""


def wget(
    url,
    dest,
    transform_func="http_transform",
    cycles=30_000_000_000,
    max_bytes=2_000_000,
):
    """Download a URL to a file on the canister filesystem.

    This is a generator function for use in async task steps::

        yield from basilisk.io.wget('https://example.com/script.py', '/script.py')

    Or with ``yield from`` inside an ``async_task()`` generator::

        def async_task():
            yield from wget('https://example.com/script.py', '/script.py')

    Args:
        url: The URL to download.
        dest: Destination file path on the canister filesystem.
        transform_func: Name of the canister's HTTP transform query method.
            Defaults to ``'http_transform'``.
        cycles: Cycles to attach to the HTTP outcall. Defaults to 30B.
        max_bytes: Maximum response size in bytes. Defaults to 2MB (IC limit).

    Returns:
        A status string like ``'Downloaded 197 bytes to /script.py'``.

    Raises:
        RuntimeError: If the HTTP request fails.

    Note:
        The canister must expose an ``http_transform`` query method (or
        whatever name is passed via *transform_func*) that strips
        non-deterministic headers for consensus.
    """
    from basilisk import ic
    from basilisk.canisters.management import management_canister

    resp = yield management_canister.http_request(
        {
            "url": url,
            "max_response_bytes": max_bytes,
            "method": {"get": None},
            "headers": [
                {"name": "User-Agent", "value": "Basilisk/1.0"},
                {"name": "Accept-Encoding", "value": "identity"},
            ],
            "body": None,
            "transform": {
                "function": (ic.id(), transform_func),
                "context": bytes(),
            },
        }
    ).with_cycles(cycles)

    if "Ok" in resp:
        body = resp["Ok"]["body"]
        import os

        parent = os.path.dirname(dest)
        if parent and parent != "/":
            os.makedirs(parent, exist_ok=True)
        with open(dest, "wb") as f:
            f.write(body if isinstance(body, bytes) else body.encode("utf-8"))
        return f"Downloaded {len(body)} bytes to {dest}"
    else:
        raise RuntimeError(f"Download failed: {resp}")
