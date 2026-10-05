"""Read secrets/server-access.txt and probe the 115 server, read-only.

Deliberately does nothing but look: connects, reports what it finds, and touches
no data. Run this before any export so a credential typo surfaces here rather than
two hours into a panel build.

    python -X utf8 scripts/dev/test_server_access.py
    python -X utf8 scripts/dev/test_server_access.py --check-credentials   # parse only
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CREDENTIALS = ROOT / "secrets" / "server-access.txt"

REQUIRED = ("host", "user")
PROBES = [
    ("主机名 / 内核", "hostname && uname -sr"),
    ("CPU 核数", "nproc"),
    ("内存", "free -g | head -2"),
    ("磁盘（工作目录所在分区）", "df -h . | tail -1"),
    ("conda", "conda env list 2>/dev/null || echo '(未找到 conda)'"),
    ("python", "python -V 2>&1 || echo '(未找到 python)'"),
    (
        "rqdatac 版本",
        "${PY:-python} -c \"import rqdatac; print(rqdatac.__version__)\" 2>&1 "
        "|| echo '(import 失败)'",
    ),
    ("RQDATA 环境变量", 'echo "RQDATAC_CONF=${RQDATAC_CONF:-<未设置>}"'),
    ("日期范围（服务器当前时间）", "date -Is"),
]


def load_credentials(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(f"凭据文件不存在：{path}")
    values: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            print(f"  警告：第 {number} 行没有 '='，已忽略：{stripped[:50]}")
            continue
        key, _, value = stripped.partition("=")
        values[key.strip().lower()] = value.strip()
    return values


def build_ssh_command(creds: dict[str, str], remote: str) -> list[str]:
    command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
               "-o", "StrictHostKeyChecking=accept-new"]
    if creds.get("port"):
        command += ["-p", creds["port"]]
    if creds.get("identity_file"):
        command += ["-i", creds["identity_file"]]
    if creds.get("jump_host"):
        jump = creds["jump_user"] + "@" + creds["jump_host"] if creds.get("jump_user") else creds["jump_host"]
        command += ["-J", jump]
    command.append(f"{creds['user']}@{creds['host']}")
    command.append(remote)
    return command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", default=str(CREDENTIALS))
    parser.add_argument("--check-credentials", action="store_true",
                        help="only parse the file; do not connect")
    args = parser.parse_args(argv)

    creds = load_credentials(Path(args.credentials))
    print(f"凭据文件：{args.credentials}")
    for key in ("host", "port", "user", "conda_env", "rqdata_dir", "cores", "work_dir"):
        value = creds.get(key, "")
        shown = value if key not in ("password", "passphrase") else ("*" * len(value) if value else "")
        print(f"  {key:<14}= {shown or '(空)'}")
    print(f"  identity_file = {creds.get('identity_file') or '(空)'}")
    print(f"  password      = {'已填（未显示）' if creds.get('password') else '(空)'}")

    missing = [key for key in REQUIRED if not creds.get(key)]
    if missing:
        print(f"\n❌ 还缺：{', '.join(missing)}")
        return 2

    if creds.get("identity_file") and not Path(creds["identity_file"]).is_file():
        print(f"\n❌ 私钥文件在本机找不到：{creds['identity_file']}")
        return 2
    if not creds.get("identity_file") and not creds.get("password"):
        print("\n❌ 没有私钥路径也没有密码，无法登录")
        return 2

    if args.check_credentials:
        print("\n✅ 凭据格式完整（未连接，按要求跳过）")
        return 0

    if creds.get("password") and not creds.get("identity_file"):
        print("\n⚠️ 只填了密码：本脚本用 ssh 密钥模式测试，不会用密码。")
        print("   要么把私钥放到本机并填 identity_file，要么在服务器上配置好密钥登录。")
        return 2

    print(f"\n连接 {creds['user']}@{creds['host']} ……")
    failures = 0
    for label, remote in PROBES:
        completed = subprocess.run(
            build_ssh_command(creds, remote), capture_output=True, text=True, timeout=60
        )
        output = (completed.stdout or "").strip()
        error = (completed.stderr or "").strip()
        if completed.returncode != 0:
            failures += 1
            print(f"  ✗ {label}: {error.splitlines()[-1] if error else 'exit ' + str(completed.returncode)}")
        else:
            print(f"  ✓ {label}: {output.splitlines()[0] if output else '(空)'}")
            for extra in output.splitlines()[1:6]:
                print(f"      {extra}")

    if failures and failures == len(PROBES):
        print("\n❌ 全部失败 —— 大概率是地址/用户/密钥不对，或本机到服务器网络不通。")
        return 1
    print(f"\n{'⚠️ 部分探测失败' if failures else '✅ 连接正常'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
