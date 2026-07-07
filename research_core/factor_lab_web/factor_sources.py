from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Protocol


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class FactorSourceDiagnostic:
    level: str
    source_type: str
    source_id: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "level": self.level,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "message": self.message,
        }


class FactorSource(Protocol):
    """Read factor definitions from one source.

    A source only describes what factors exist. It must not run factor
    calculations, truth checks, or strategy research.
    """

    source_type: str

    def collect(self) -> list[dict[str, Any]]:
        """Return normalized factor definition dictionaries."""


class SpecsPyFactorSource:
    """Collect factor definitions from research_core/factor_lab/libraries/*/specs.py."""

    source_type = "specs_py"

    def __init__(self, libraries_dir: Path | None = None) -> None:
        self.libraries_dir = libraries_dir or Path(__file__).resolve().parents[1] / "factor_lab" / "libraries"
        self.diagnostics: list[FactorSourceDiagnostic] = []

    def collect(self) -> list[dict[str, Any]]:
        self.diagnostics = []
        specs: list[dict[str, Any]] = []
        for specs_path in self.libraries_dir.glob("*/specs.py"):
            module = self._load_specs_module(specs_path)
            if module is None:
                continue
            source_id = str(specs_path.relative_to(self.libraries_dir.parent))
            for item in self._iter_module_specs(module, specs_path=specs_path):
                specs.append(_spec_from_any(item, source_type=self.source_type, source_id=source_id))
        return specs

    def _load_specs_module(self, specs_path: Path) -> Any | None:
        library_dir = specs_path.parent.name
        module_name = f"research_core.factor_lab.libraries.{library_dir}.specs"
        failures: list[str] = []
        try:
            return importlib.import_module(module_name)
        except Exception as exc:
            failures.append(f"import_module failed: {exc}")

        fallback_name = f"_factor_lab_web_{library_dir}_specs"
        try:
            spec = importlib.util.spec_from_file_location(fallback_name, specs_path)
            if spec is None or spec.loader is None:
                self._warn(specs_path, "cannot create import spec or loader")
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception as exc:
            failures.append(f"file import failed: {exc}")
            self._warn(specs_path, "; ".join(failures))
            return None

    def _iter_module_specs(self, module: Any, *, specs_path: Path) -> list[Any]:
        items: list[Any] = []
        for name, value in vars(module).items():
            if name.startswith("_"):
                continue
            if callable(value) and (name == "specs" or name.endswith("_specs")):
                result = self._call_zero_arg_specs(value, specs_path=specs_path, function_name=name)
                if isinstance(result, list | tuple):
                    items.extend(result)
                elif result is not None:
                    self._warn(specs_path, f"{name}() returned {type(result).__name__}, expected list or tuple")
            elif isinstance(value, list | tuple) and ("SPEC" in name.upper() or "FACTOR" in name.upper()):
                items.extend(value)
        return items

    def _call_zero_arg_specs(self, value: Any, *, specs_path: Path, function_name: str) -> Any:
        try:
            signature = inspect.signature(value)
        except (TypeError, ValueError) as exc:
            self._warn(specs_path, f"cannot inspect {function_name}() signature: {exc}")
            return None
        required = [
            parameter
            for parameter in signature.parameters.values()
            if parameter.default is inspect.Parameter.empty
            and parameter.kind
            in {
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            }
        ]
        if required:
            required_names = ", ".join(parameter.name for parameter in required)
            self._warn(specs_path, f"{function_name}() requires arguments and was skipped: {required_names}")
            return None
        try:
            return value()
        except Exception as exc:
            self._warn(specs_path, f"{function_name}() raised {type(exc).__name__}: {exc}")
            return None

    def _warn(self, specs_path: Path, message: str) -> None:
        source_id = str(specs_path)
        self.diagnostics.append(
            FactorSourceDiagnostic(
                level="warning",
                source_type=self.source_type,
                source_id=source_id,
                message=message,
            )
        )
        LOGGER.warning("Factor source warning in %s: %s", source_id, message)


def configured_factor_sources() -> list[FactorSource]:
    """Return the active factor definition sources.

    Add future sources here, for example a JSON registry source for factors
    generated by literature crawling, factor synthesis, or automated mining.
    """

    return [SpecsPyFactorSource()]


def collect_factor_specs(sources: list[FactorSource] | None = None) -> list[dict[str, Any]]:
    specs, _diagnostics = collect_factor_specs_with_diagnostics(sources=sources)
    return specs


def collect_factor_specs_with_diagnostics(
    sources: list[FactorSource] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    specs: list[dict[str, Any]] = []
    diagnostics: list[dict[str, str]] = []
    for source in sources or configured_factor_sources():
        specs.extend(source.collect())
        diagnostics.extend(diagnostic.as_dict() for diagnostic in getattr(source, "diagnostics", []))
    return specs, diagnostics


def _spec_from_any(item: Any, *, source_type: str, source_id: str) -> dict[str, Any]:
    if isinstance(item, dict):
        return _spec_from_mapping(item, source_type=source_type, source_id=source_id)
    if is_dataclass(item):
        return _spec_from_mapping(asdict(item), source_type=source_type, source_id=source_id)

    mapping: dict[str, Any] = {}
    for key in [
        "factor_name",
        "name",
        "factor_id",
        "display_name",
        "library",
        "required_fields",
        "formula",
        "description",
        "source_document",
        "tags",
        "metadata",
        "category",
        "factor_category",
        "subcategory",
        "status",
    ]:
        if hasattr(item, key):
            mapping[key] = getattr(item, key)
    return _spec_from_mapping(mapping, source_type=source_type, source_id=source_id)


def _spec_from_mapping(item: dict[str, Any], *, source_type: str, source_id: str) -> dict[str, Any]:
    raw_library = str(item.get("library") or "")
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    return {
        "factor_name": str(item.get("factor_name") or item.get("name") or ""),
        "factor_id": str(item.get("factor_id") or ""),
        "display_name": str(item.get("display_name") or ""),
        "library": _display_library(raw_library),
        "raw_library": raw_library,
        "required_fields": list(item.get("required_fields") or []),
        "formula": item.get("formula") or "",
        "description": item.get("description") or "",
        "source_document": item.get("source_document") or "",
        "tags": list(item.get("tags") or []),
        "category": item.get("category") or item.get("factor_category") or metadata.get("category") or "",
        "subcategory": item.get("subcategory") or metadata.get("subcategory") or "",
        "metadata": metadata,
        "source": source_type,
        "source_id": source_id,
        "implementation_status": item.get("status") or metadata.get("status") or "registered",
        "metric_libraries": [raw_library],
    }


def _display_library(library: str) -> str:
    normalized = library.lower()
    if normalized == "alpha101":
        return "WQ101"
    if normalized in {"gtja191", "alpha191"}:
        return "GTJA191"
    if normalized in {"quantapi33", "quantapi", "quant_api", "quant api"}:
        return "Quant API"
    if not library:
        return "User Custom"
    return library
