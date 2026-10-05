"""Upload the repository to the 115 server as a git archive.

Only tracked files go up, so nothing gitignored (data/, runtime/, secrets/) is
copied. Uses the committed tree rather than the working directory: the server
should run the same revision CI ran.

    python -X utf8 scripts/dev/upload_repo.py --remote-dir /home/data/agentmatrix_run/agentmatrix
"""

from __future__ import annotations

import argparse
import subprocess
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote-dir", default="/home/data/agentmatrix_run/agentmatrix")
    parser.add_argument("--archive", default=".tmp-repo.tar")
    parser.add_argument("--keep-archive", action="store_true")
    args = parser.parse_args(argv)

    archive = ROOT / args.archive
    revision = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    print(f"uploading revision {revision}")

    # Refuse to upload a dirty tree: the server must run exactly what was verified.
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    if dirty:
        print("working tree is dirty; commit first so the server runs a known revision")
        print(dirty[:600])
        return 2

    subprocess.run(["git", "archive", "--format=tar", "-o", str(archive), "HEAD"],
                   cwd=ROOT, check=True)
    size_mb = archive.stat().st_size / 1024 / 1024
    print(f"archive: {archive} ({size_mb:.1f} MB)")

    creds = load_credentials(CREDENTIALS)
    port = creds.get("port", "22")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=creds["host"], port=int(port) if port.isdigit() else 22,
        username=creds["user"], password=creds.get("password") or None,
        timeout=30, look_for_keys=False, allow_agent=False,
    )
    try:
        def run(command: str, timeout: int = 900) -> tuple[int, str, str]:
            _in, out, err = client.exec_command(command, timeout=timeout)
            return (out.channel.recv_exit_status(),
                    out.read().decode("utf-8", "replace"),
                    err.read().decode("utf-8", "replace"))

        code, out, err = run(f"mkdir -p {args.remote_dir} && rm -rf {args.remote_dir}/*")
        if code != 0:
            print(f"mkdir failed: {err}")
            return 1

        print(f"uploading to {args.remote_dir} ...")
        sftp = client.open_sftp()
        remote_archive = f"{args.remote_dir}.tar"
        sftp.put(str(archive), remote_archive)
        sftp.close()
        print("  uploaded")

        code, out, err = run(
            f"cd {args.remote_dir} && tar xf {remote_archive} && rm -f {remote_archive} "
            f"&& echo 'extracted' && ls | head -20"
        )
        print(out.strip())
        if code != 0:
            print(f"extract failed: {err}")
            return 1

        code, out, _ = run(f"cd {args.remote_dir} && git rev-parse --short HEAD 2>/dev/null; "
                           f"cat configs/validation_gates.yaml | head -5")
        print("--- sanity ---")
        print(out.strip()[:400])
    finally:
        client.close()

    if not args.keep_archive:
        archive.unlink(missing_ok=True)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
