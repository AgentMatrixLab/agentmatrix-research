import pathlib
import re

p = pathlib.Path("scripts/dev/run_downstream.sh")
s = p.read_text(encoding="utf-8")
print("CRLF count:", s.count("\r"))
print("BATCH_CANDIDATES uses:", len(re.findall(r"\$BATCH_CANDIDATES", s)))
print()
print("步骤顺序:")
for line in s.splitlines():
    if line.startswith('step "'):
        print("  ", line.strip())
print()
print("阶段脚本引用:")
for name in (
    "merge_batch_manifests", "build_batch_candidates", "consolidate_factor_values",
    "run_robustness_supplement", "build_strategy_demos", "build_delivery_manifest",
    "build_live_signals", "package_delivery", "cross_check_delivery",
):
    print("  %-28s %d" % (name, s.count(name)))
print()
print("关键参数:")
for token in ("--clusters-json", "--jobs", "--candidates", "--output-dir", "--summary-out"):
    print("  %-18s %d" % (token, s.count(token)))
