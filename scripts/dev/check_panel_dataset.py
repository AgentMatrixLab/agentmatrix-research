"""Final consistency check on the generated Factor Console dataset."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
payload = json.loads(
    (ROOT / "pages/factor-panel/data/panel.json").read_text(encoding="utf-8")
)

readiness = payload["catalog"]["readiness"]
print("code commit   :", payload["code_commit"])
print("generated at  :", payload["generated_at"])
print("catalog       :", payload["catalog"]["total"])
print(
    "readiness     :",
    readiness["counts"],
    "=> runnable",
    readiness["runnable"],
    f"({readiness['runnable_ratio']:.1%})",
)
print("factors rows  :", len(payload["factors"]))
print("funnel        :")
for stage in payload["funnel"]:
    print(f"    {stage['key']:<14} {stage['count']:>5}  [{stage['status']}]")
print("validation runs found:", payload["honesty"]["validation_runs_found"])
print("delivery      :", payload["delivery"])
