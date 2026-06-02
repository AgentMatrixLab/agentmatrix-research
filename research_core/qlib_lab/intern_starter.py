from __future__ import annotations

import json
from dataclasses import asdict

from research_core.qlib_lab.workflow import Alpha158WorkflowConfig, export_alpha158_template, run_alpha158_workflow


def generate_starter_pack(output_path: str | None = None) -> dict[str, str]:
    config = Alpha158WorkflowConfig()
    template_path = export_alpha158_template(config=config, output_path=output_path)
    return {
        "template_path": template_path,
        "next_step": "Run `python -m research_core.qlib_lab.cli alpha158-starter` after qlib data is ready.",
    }


def main() -> None:
    payload = {
        "starter_pack": generate_starter_pack(),
        "default_config": asdict(Alpha158WorkflowConfig()),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
