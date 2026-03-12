#!/usr/bin/env python3
"""
bosh-sshd — SSH proxy to Basilisk OS canisters.

Runs a local SSH server that spawns bosh (Basilisk OS Shell) sessions.
Connect with any SSH client to get an interactive shell inside an IC canister.

Usage:
    python -m basilisk.bosh_sshd --canister <id> [--network <net>] [--port 2222]

Then connect:
    ssh -p 2222 -o StrictHostKeyChecking=no localhost
"""

import argparse
import asyncio
import os
import sys

import asyncssh


class BoshSSHServer(asyncssh.SSHServer):
    """SSH server that authenticates all connections (dev mode)."""

    def connection_made(self, conn):
        self._conn = conn

    def connection_lost(self, exc):
        pass

    def begin_auth(self, username):
        # No auth required in dev mode — accept everyone
        return False

    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        # Accept any password in dev mode
        return True


def _make_process_factory(canister: str, network: str, bosh_module_dir: str):
    """Create a factory that spawns bosh as the SSH shell process."""

    async def process_factory(process):
        """Called when a client requests a shell or exec channel."""
        cmd = [
            sys.executable, "-u", "-m", "basilisk.bosh",
            "--canister", canister,
        ]
        if network:
            cmd.extend(["--network", network])

        # If the client sent a specific command (ssh host 'command'),
        # pass it to bosh with -c. Otherwise, force interactive mode.
        command = process.command
        if command:
            cmd.extend(["-c", command])
        else:
            cmd.append("--login")

        env = {**os.environ, "PYTHONPATH": bosh_module_dir, "PYTHONUNBUFFERED": "1"}

        # Spawn bosh as a subprocess
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        # Bridge SSH channel <-> subprocess
        async def ssh_to_proc():
            """Forward SSH input to subprocess stdin."""
            try:
                async for data in process.stdin:
                    if isinstance(data, str):
                        data = data.encode()
                    proc.stdin.write(data)
                    await proc.stdin.drain()
            except Exception:
                pass
            finally:
                try:
                    proc.stdin.close()
                except Exception:
                    pass

        async def proc_stdout_to_ssh():
            """Forward subprocess stdout to SSH output."""
            try:
                while True:
                    data = await proc.stdout.read(4096)
                    if not data:
                        break
                    process.stdout.write(data.decode("utf-8", errors="replace"))
            except Exception:
                pass

        async def proc_stderr_to_ssh():
            """Forward subprocess stderr to SSH stderr."""
            try:
                while True:
                    data = await proc.stderr.read(4096)
                    if not data:
                        break
                    process.stderr.write(data.decode("utf-8", errors="replace"))
            except Exception:
                pass

        try:
            await asyncio.gather(ssh_to_proc(), proc_stdout_to_ssh(), proc_stderr_to_ssh())
            await proc.wait()
            process.exit(proc.returncode or 0)
        except (asyncssh.BreakReceived, asyncssh.TerminalSizeChanged):
            pass
        except Exception:
            process.exit(1)

    return process_factory


async def start_server(canister: str, network: str, port: int, host_key_path: str):
    """Start the SSH server."""

    # Generate host key if it doesn't exist
    if not os.path.exists(host_key_path):
        print(f"Generating SSH host key: {host_key_path}", file=sys.stderr)
        import subprocess
        subprocess.run(
            ["ssh-keygen", "-t", "rsa", "-b", "2048", "-f", host_key_path, "-N", "", "-q"],
            check=True,
        )

    # Resolve the directory containing the basilisk package
    bosh_module_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    net_label = network or "local"
    print(f"bosh-sshd starting", file=sys.stderr)
    print(f"  Canister: {canister}", file=sys.stderr)
    print(f"  Network:  {net_label}", file=sys.stderr)
    print(f"  Port:     {port}", file=sys.stderr)
    print(f"  Host key: {host_key_path}", file=sys.stderr)
    print(f"", file=sys.stderr)
    print(f"Connect with:", file=sys.stderr)
    print(f"  ssh -p {port} -o StrictHostKeyChecking=no localhost", file=sys.stderr)
    print(f"", file=sys.stderr)
    print(f"Or run a single command:", file=sys.stderr)
    print(f"  ssh -p {port} -o StrictHostKeyChecking=no localhost 'print(1+1)'", file=sys.stderr)
    print(f"", file=sys.stderr)
    print(f"SFTP (canister filesystem):", file=sys.stderr)
    print(f"  sftp -P {port} -o StrictHostKeyChecking=no localhost", file=sys.stderr)
    sys.stderr.flush()

    process_factory = _make_process_factory(canister, network, bosh_module_dir)

    # SFTP factory: creates a CanisterSFTPServer per connection
    from basilisk.bosh_sftp import CanisterSFTPServer

    def sftp_factory(conn):
        return CanisterSFTPServer(conn, canister, network)

    await asyncssh.create_server(
        BoshSSHServer, "", port,
        server_host_keys=[host_key_path],
        process_factory=process_factory,
        sftp_factory=sftp_factory,
    )


async def async_main(canister: str, network: str, port: int, host_key_path: str):
    await start_server(canister, network, port, host_key_path)
    # Run forever
    await asyncio.Future()


def main():
    parser = argparse.ArgumentParser(
        prog="bosh-sshd",
        description="SSH proxy to Basilisk OS canisters",
    )
    parser.add_argument("--canister", required=True, help="Canister name or ID")
    parser.add_argument("--network", default=None, help="Network: local, ic, or URL")
    parser.add_argument("--port", type=int, default=2222, help="SSH port (default: 2222)")
    parser.add_argument("--host-key", default="/tmp/bosh_host_key",
                        help="Path to SSH host key (auto-generated if missing)")

    args = parser.parse_args()

    try:
        asyncio.run(async_main(args.canister, args.network, args.port, args.host_key))
    except KeyboardInterrupt:
        print("\nbosh-sshd stopped.", file=sys.stderr)
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"Error: port {args.port} already in use. Try --port <other>", file=sys.stderr)
            sys.exit(1)
        raise


if __name__ == "__main__":
    main()
