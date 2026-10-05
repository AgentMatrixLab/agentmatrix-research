"""Upload the repository to the 115 server as a git archive.

Only tracked files go up, so nothing gitignored (data/, runtime/, secrets/) is
copied. Uses the committed tree rather than the working directory: the server
should run the same revision CI ran.

Runtime data is PRESERVED across the upload. The server keeps accumulated
evidence *inside* the deploy directory -- `configs/validation_gates.yaml` puts
per-factor results under `<repo>/data/factor_lab/validation_runs`, and the server
tree is not a git checkout, so that evidence is untracked and would otherwise be
destroyed by the wipe-and-extract. That happened for real: an upload during the
213-shard run deleted the results of every shard that had already finished, and
because scoring and FDR both read that directory the delivery would have been
built from the few results that happened to land afterwards.

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

#: Directories that hold accumulated runtime evidence and must survive an upload.
PRESERVED = ("data", "runtime", "logs")


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
    # The FULL sha, not `--short`: `_git_commit()` records this verbatim into every run
    # manifest, and the delivery cross-check requires a 40-char hex commit.
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    short = revision[:7]
    print(f"uploading revision {short} ({revision})")

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

        # Move runtime evidence out, wipe, extract, move it back. Without this the wipe
        # below deletes every validation result accumulated so far, and the failure is
        # silent: the delivery is then scored and FDR-corrected over whatever survived.
        preserve = f"{args.remote_dir}.deploy_preserve"
        names = " ".join(PRESERVED)
        code, out, err = run(
            f"set -e; "
            f"mkdir -p {args.remote_dir}; "
            f"rm -rf {preserve}; mkdir -p {preserve}; "
            f"for name in {names}; do "
            f"  if [ -e {args.remote_dir}/$name ]; then mv {args.remote_dir}/$name {preserve}/$name; fi; "
            f"done; "
            f"rm -rf {args.remote_dir}; mkdir -p {args.remote_dir}; "
            f"tar xf {remote_archive} -C {args.remote_dir}; "
            f"rm -f {remote_archive}; "
            f"for name in {names}; do "
            f"  if [ -e {preserve}/$name ]; then "
            f"    if [ -e {args.remote_dir}/$name ]; then "
            f"      cp -an {preserve}/$name/. {args.remote_dir}/$name/ || true; "
            f"    else mv {preserve}/$name {args.remote_dir}/$name; fi; "
            f"  fi; "
            f"done; "
            f"rm -rf {preserve}; "
            f"echo '{revision}' > {args.remote_dir}/COMMIT; "
            f"echo extracted; cat {args.remote_dir}/COMMIT",
            timeout=1800,
        )
        print(out.strip())
        if code != 0:
            print(f"extract failed: {err}")
            return 1

        # Report what runtime evidence survived, so a wipe can never again go unnoticed.
        code, out, _ = run(
            f"echo '--- preserved runtime data ---'; "
            f"for name in {names}; do "
            f"  if [ -e {args.remote_dir}/$name ]; then "
            f"    echo \"  $name: $(find {args.remote_dir}/$name -type f | wc -l) files\"; "
            f"  else echo \"  $name: (absent)\"; fi; "
            f"done"
        )
        print(out.strip())

        code, out, _ = run(f"cd {args.remote_dir} && cat configs/validation_gates.yaml | head -3")
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
