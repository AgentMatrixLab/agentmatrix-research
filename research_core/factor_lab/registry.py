from __future__ import annotations

import json
from dataclasses import asdict
from typing import Iterable

from contracts.factor_research import FactorResearchSpec
from research_core.factor_lab.runtime import FactorLabWorkspaceConfig, now_iso


def serialize_specs(specs: Iterable[FactorResearchSpec]) -> list[dict[str, object]]:
    return [asdict(spec) for spec in specs]


def build_catalog(specs: Iterable[FactorResearchSpec]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for spec in specs:
        items.append(
            {
                "factor_name": spec.factor_name,
                "display_name": spec.display_name or spec.factor_name,
                "library": spec.library,
                "factor_id": spec.factor_id,
                "version": spec.version,
                "frequency": spec.frequency,
                "required_fields": list(spec.required_fields),
                "status": spec.metadata.get("status", "planned"),
                "implementation_stage": spec.metadata.get("implementation_stage", "spec"),
                "source_document": spec.source_document,
                "tags": list(spec.tags),
            }
        )
    return items


def export_library_specs(
    *,
    config: FactorLabWorkspaceConfig,
    library: str,
    specs: Iterable[FactorResearchSpec],
) -> dict[str, object]:
    config.ensure_directories()
    spec_list = list(specs)
    payload = {
        "library": library,
        "exported_at": now_iso(),
        "count": len(spec_list),
        "items": serialize_specs(spec_list),
    }
    catalog = {
        "library": library,
        "exported_at": payload["exported_at"],
        "count": len(spec_list),
        "items": build_catalog(spec_list),
    }
    config.specs_path(library).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    config.catalog_path(library).write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "specs_path": str(config.specs_path(library)),
        "catalog_path": str(config.catalog_path(library)),
        "count": len(spec_list),
    }
