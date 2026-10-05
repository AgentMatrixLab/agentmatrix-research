RUN=/home/data/agentmatrix_run
mkdir -p "$RUN"

cat > "$RUN/mirror_runtime_data.py" <<'PYEOF'
"""Mirror the server's runtime evidence outside the deploy directory."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

CN_TZ = timezone(timedelta(hours=8))


def mirror_tree(source: Path, target: Path) -> dict:
    copied = skipped = failed = 0
    bytes_copied = 0
    if not source.exists():
        return {"copied": 0, "skipped": 0, "failed": 0, "bytes": 0, "source_present": False}
    for root, _dirs, files in os.walk(source):
        relative = Path(root).relative_to(source)
        destination_dir = target / relative
        for name in files:
            candidate = Path(root) / name
            destination = destination_dir / name
            try:
                stat = candidate.stat()
            except OSError:
                failed += 1
                continue
            if destination.exists():
                try:
                    existing = destination.stat()
                    if existing.st_size == stat.st_size and existing.st_mtime >= stat.st_mtime:
                        skipped += 1
                        continue
                except OSError:
                    pass
            try:
                destination_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidate, destination)
                copied += 1
                bytes_copied += stat.st_size
            except OSError:
                failed += 1
    return {"copied": copied, "skipped": skipped, "failed": failed, "bytes": bytes_copied,
            "source_present": True}


def count_files(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(len(files) for _root, _dirs, files in os.walk(root))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="/home/data/agentmatrix_run/agentmatrix")
    parser.add_argument("--mirror-root", default="/home/data/agentmatrix_run/runtime_mirror")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--status", default="")
    args = parser.parse_args(argv)

    repo = Path(args.repo)
    mirror_root = Path(args.mirror_root)
    source = repo / "data"
    target = mirror_root / "data"
    status_path = Path(args.status) if args.status else mirror_root / "mirror_status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)

    passes = 0
    while True:
        passes += 1
        result = mirror_tree(source, target)
        stamp = repo / "COMMIT"
        if stamp.is_file():
            try:
                shutil.copy2(stamp, mirror_root / "COMMIT")
            except OSError:
                pass
        runs = target / "factor_lab" / "validation_runs"
        status = {
            "updated_at": datetime.now(CN_TZ).isoformat(timespec="seconds"),
            "passes": passes,
            "source": str(source),
            "target": str(target),
            "results_in_source": count_files(runs),
            "results_in_mirror": count_files(runs),
            **result,
        }
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[%s] pass %d: source_runs=%d mirror_runs=%d copied=%d failed=%d" % (
            status["updated_at"], passes, status["results_in_source"],
            status["results_in_mirror"], result["copied"], result["failed"]), flush=True)
        if args.once:
            return 0
        time.sleep(max(5, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
PYEOF

PY=/home/data/conda-envs/rqsdk/bin/python
echo "=== 首次同步（一次性）==="
$PY -X utf8 "$RUN/mirror_runtime_data.py" --once

echo
echo "=== 启动常驻守护 ==="
pkill -f 'mirror_runtime_data.py --interval' 2>/dev/null
sleep 1
setsid nohup $PY -X utf8 "$RUN/mirror_runtime_data.py" --interval 60 \
  > "$RUN/logs/mirror.log" 2>&1 < /dev/null &
echo "  mirror pid=$!"
sleep 8
echo "--- mirror.log ---"
tail -5 "$RUN/logs/mirror.log"

echo
echo "=== 校验镜像 ==="
echo "  源  validation_result.json : $(find $RUN/agentmatrix/data/factor_lab/validation_runs -name validation_result.json 2>/dev/null | wc -l)"
echo "  镜像 validation_result.json : $(find $RUN/runtime_mirror/data/factor_lab/validation_runs -name validation_result.json 2>/dev/null | wc -l)"
echo "  镜像 sha 抽查:"
md5sum $RUN/agentmatrix/data/factor_lab/validation_runs/*/validation_result.json 2>/dev/null | head -3
md5sum $RUN/runtime_mirror/data/factor_lab/validation_runs/*/validation_result.json 2>/dev/null | head -3
echo
echo "=== 当前 pool 进度 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)"
ps -eo pid,etime,args | awk '$0 !~ /mirror_runtime/ && /run_one_shard\.sh/ {print "  " $1, $2, $4, $5}'
date -Is
