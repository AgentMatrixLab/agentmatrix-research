import pathlib
import re

p = pathlib.Path("scripts/dev/run_downstream.sh")
s = p.read_text(encoding="utf-8")
print("CRLF count:", s.count("\r"))
print("BATCH_CANDIDATES uses:", len(re.findall(r"\$BATCH_CANDIDATES", s)))
print("step 6 present:", 'step "6.' in s)
print("final count block present:", "IN DELIVERY PACKAGE" in s)
print("build_batch_candidates referenced:", s.count("build_batch_candidates"))
print("cross_check referenced:", s.count("cross_check_delivery"))
