"""Run a read-only command on the 115 server over SSH.

Credentials come from secrets/server-access.txt, which is gitignored. The password
is never printed and never written to any output file.

    python -X utf8 scripts/dev/ssh_run.py "hostname; nproc"
    python -X utf8 scripts/dev/ssh_run.py --file scripts/dev/recon/01_system.sh
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[2]
CREDENTIALS = ROOT / "secrets" / "server-access.txt"


def load_credentials(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip().lower()] = value.strip()
    return values


def connect(creds: dict[str, str]) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    port = creds.get("port", "22")
    if not port.isdigit():
        port = "22"
    client.connect(
        hostname=creds["host"],
        port=int(port),
        username=creds["user"],
        password=creds.get("password") or None,
        key_filename=creds.get("identity_file") or None,
        timeout=30,
        banner_timeout=30,
        auth_timeout=30,
        look_for_keys=False,
        allow_agent=False,
    )
    return client


def run(client: paramiko.SSHClient, command: str, timeout: int = 600) -> tuple[int, str, str]:
    _stdin, stdout, stderr = client.exec_command(command, timeout=timeout, get_pty=False)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    return stdout.channel.recv_exit_status(), out, err


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="")
    parser.add_argument("--file", default="", help="run a local script on the server")
    parser.add_argument(
        "--put",
        action="append",
        default=[],
        metavar="LOCAL:REMOTE",
        help="upload a local file before running (repeatable; splits on the last colon)",
    )
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--quiet-stderr", action="store_true")
    args = parser.parse_args(argv)

    if args.file:
        command = Path(args.file).read_text(encoding="utf-8")
    elif args.command:
        command = args.command
    elif args.put:
        command = "true"
    else:
        parser.error("give a command, --file, or --put")

    creds = load_credentials(CREDENTIALS)
    client = connect(creds)
    try:
        if args.put:
            sftp = client.open_sftp()
            try:
                for spec in args.put:
                    local_name, _, remote_name = spec.rpartition(":")
                    if not local_name or not remote_name:
                        parser.error(f"--put wants LOCAL:REMOTE, got {spec!r}")
                    local_path = Path(local_name)
                    if not local_path.is_file():
                        parser.error(f"local file does not exist: {local_path}")
                    sftp.put(str(local_path), remote_name)
                    print(f"put {local_path.name} -> {remote_name}", file=sys.stderr)
            finally:
                sftp.close()
        code, out, err = run(client, command, args.timeout)
    finally:
        client.close()

    if out:
        print(out, end="" if out.endswith("\n") else "\n")
    if err and not args.quiet_stderr:
        print("--- stderr ---", file=sys.stderr)
        print(err, end="" if err.endswith("\n") else "\n", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
