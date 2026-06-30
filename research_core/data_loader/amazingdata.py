from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from contracts.factor_research import (
    DataQualityIssue,
    DataQualityReport,
    DataSourceSpec,
    PanelRequest,
    PanelSnapshot,
)
from research_core.data_loader.market_data import resolve_universe as resolve_market_universe


DEFAULT_ENV_FILE = Path.home() / ".config/db4quant/smartdata_ro.env"
DEFAULT_DATABASE = "amazingdata"
DEFAULT_PRICE_TABLE = "ods_kline_1d"
DEFAULT_SECURITY_TABLE = "ref_security"
DEFAULT_STATUS_TABLE = "ods_security_status_daily"
REQUIRED_PANEL_COLUMNS = ["date", "code", "open", "high", "low", "close", "volume", "amount", "vwap"]
NUMERIC_PANEL_COLUMNS = ["open", "high", "low", "close", "volume", "amount", "vwap"]


@dataclass(frozen=True)
class AmazingDataConfig:
    host: str = "127.0.0.1"
    port: int = 19000
    user: str = ""
    password: str = ""
    database: str = DEFAULT_DATABASE
    price_table: str = DEFAULT_PRICE_TABLE
    security_table: str = DEFAULT_SECURITY_TABLE
    status_table: str = DEFAULT_STATUS_TABLE

    @classmethod
    def from_env_file(cls, path: str | Path = DEFAULT_ENV_FILE) -> "AmazingDataConfig":
        values = load_env_file(path)
        return cls(
            host=values.get("SMARTDATA_CH_HOST", "127.0.0.1"),
            port=int(values.get("SMARTDATA_CH_PORT", "19000")),
            user=values.get("SMARTDATA_CH_USER", ""),
            password=values.get("SMARTDATA_CH_PASSWORD", ""),
            database=values.get("SMARTDATA_CH_DATABASE", DEFAULT_DATABASE),
            price_table=values.get("SMARTDATA_CH_PRICE_TABLE", DEFAULT_PRICE_TABLE),
            security_table=values.get("SMARTDATA_CH_SECURITY_TABLE", DEFAULT_SECURITY_TABLE),
            status_table=values.get("SMARTDATA_CH_STATUS_TABLE", DEFAULT_STATUS_TABLE),
        )

    def redacted(self) -> dict[str, Any]:
        payload = asdict(self)
        if payload.get("password"):
            payload["password"] = "***"
        return payload


def load_env_file(path: str | Path) -> dict[str, str]:
    env_path = Path(path)
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def create_client(config: AmazingDataConfig):
    try:
        from clickhouse_driver import Client
    except ImportError as exc:
        raise ImportError("clickhouse_driver is required for amazingdata ClickHouse access") from exc
    return Client(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        connect_timeout=5,
        send_receive_timeout=90,
    )


def parse_symbol_list(raw: str | Sequence[str] | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [item.strip() for item in raw.split(",") if item.strip()]
    return [str(item).strip() for item in raw if str(item).strip()]


def _symbol_variants(symbol: str) -> list[str]:
    value = str(symbol).strip().upper()
    if not value:
        return []
    variants = [value]
    base = value.split(".", 1)[0]
    if len(base) == 6 and base.isdigit():
        variants.extend([base, f"{base}.SH", f"{base}.SZ", f"SH{base}", f"SZ{base}"])
    return list(dict.fromkeys(variants))


def resolve_amazingdata_universe_symbols(universe: str | Sequence[str] | None) -> list[str]:
    """Resolve an index universe to ClickHouse symbol candidates.

    ``all``/``listed`` intentionally means no index filter. Named index
    universes are resolved through the existing market-data resolver and then
    expanded to common A-share code formats before intersecting in ClickHouse.
    """
    if universe is None:
        return []
    if not isinstance(universe, str):
        raw_symbols = [str(item) for item in universe]
    else:
        label = universe.strip().lower()
        if not label or label in {"all", "listed", "listed_equities"}:
            return []
        if "," in label:
            raw_symbols = parse_symbol_list(universe)
        else:
            try:
                raw_symbols = resolve_market_universe(label)
            except Exception as exc:
                raise ValueError(
                    f"Could not resolve universe {universe!r}. "
                    "Use --universe all to select listed equities by coverage, "
                    "or pass explicit --symbols for a server-local universe."
                ) from exc
    candidates: list[str] = []
    for symbol in raw_symbols:
        candidates.extend(_symbol_variants(symbol))
    return list(dict.fromkeys(candidates))


def _identifier(value: str) -> str:
    if not value.replace("_", "").isalnum():
        raise ValueError(f"Unsafe ClickHouse identifier: {value!r}")
    return value


def _qualified(config: AmazingDataConfig, table: str) -> str:
    return f"{_identifier(config.database)}.{_identifier(table)}"


def check_connection(config: AmazingDataConfig | None = None, *, client: Any | None = None) -> dict[str, Any]:
    cfg = config or AmazingDataConfig.from_env_file()
    try:
        active_client = client or create_client(cfg)
        with redirect_stderr(StringIO()):
            rows = active_client.execute("SELECT 1")
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "config": cfg.redacted(),
        }
    return {
        "ok": bool(rows and rows[0][0] == 1),
        "config": cfg.redacted(),
    }


def select_symbols(
    client: Any,
    *,
    config: AmazingDataConfig,
    start_date: str | date,
    end_date: str | date,
    universe_symbols: Sequence[str] | None = None,
    max_symbols: int | None = 300,
    min_coverage: float = 0.95,
) -> list[str]:
    date_count = client.execute(
        f"""
        SELECT countDistinct(trade_date)
        FROM {_qualified(config, config.price_table)}
        WHERE trade_date BETWEEN %(start)s AND %(end)s
        """,
        {"start": start_date, "end": end_date},
    )[0][0]
    min_rows = max(1, int(np.ceil(float(date_count) * float(min_coverage))))
    limit_clause = "" if max_symbols is None or int(max_symbols) <= 0 else f"LIMIT {int(max_symbols)}"
    universe_candidates = tuple(dict.fromkeys(str(symbol) for symbol in universe_symbols or [] if str(symbol)))
    universe_clause = "AND k.symbol IN %(universe_symbols)s" if universe_candidates else ""
    params: dict[str, Any] = {"start": start_date, "end": end_date, "min_rows": min_rows}
    if universe_candidates:
        params["universe_symbols"] = universe_candidates
    rows = client.execute(
        f"""
        SELECT k.symbol
        FROM {_qualified(config, config.price_table)} AS k
        INNER JOIN {_qualified(config, config.security_table)} AS s ON k.symbol = s.symbol
        WHERE k.trade_date BETWEEN %(start)s AND %(end)s
          AND s.security_type = 'EQUITY'
          AND s.is_listed = 1
          {universe_clause}
        GROUP BY k.symbol
        HAVING countDistinct(k.trade_date) >= %(min_rows)s
        ORDER BY k.symbol
        {limit_clause}
        """,
        params,
    )
    return [str(row[0]) for row in rows]


def normalize_price_panel(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=REQUIRED_PANEL_COLUMNS)
    panel = raw.rename(columns={"trade_date": "date", "symbol": "code"}).copy()
    if "date" not in panel.columns or "code" not in panel.columns:
        raise ValueError("Price panel must contain date/trade_date and code/symbol columns")
    panel["date"] = pd.to_datetime(panel["date"], errors="coerce")
    panel["code"] = panel["code"].astype(str)
    for column in ["open", "high", "low", "close", "volume", "amount"]:
        if column in panel.columns:
            panel[column] = pd.to_numeric(panel[column], errors="coerce")
    if "vwap" not in panel.columns:
        volume = panel.get("volume", pd.Series(index=panel.index, dtype=float)).replace(0, np.nan)
        amount = panel.get("amount", pd.Series(index=panel.index, dtype=float))
        panel["vwap"] = amount / volume
    panel["vwap"] = pd.to_numeric(panel["vwap"], errors="coerce")
    panel = panel.dropna(subset=["date", "code"])
    panel = panel.sort_values(["code", "date"]).drop_duplicates(["date", "code"], keep="last")
    keep = [column for column in REQUIRED_PANEL_COLUMNS if column in panel.columns]
    return panel[keep].reset_index(drop=True)


def build_data_quality_report(
    panel: pd.DataFrame,
    *,
    source: str = "amazingdata",
    required_columns: Sequence[str] = REQUIRED_PANEL_COLUMNS,
    min_required_coverage: float = 0.50,
) -> DataQualityReport:
    issues: list[DataQualityIssue] = []
    if panel.empty:
        issues.append(DataQualityIssue("blocker", "non_empty", "Panel is empty."))
        return DataQualityReport(source=source, status="failed", row_count=0, issues=issues)

    missing_columns = [column for column in required_columns if column not in panel.columns]
    if missing_columns:
        issues.append(
            DataQualityIssue(
                "blocker",
                "schema",
                "Required panel columns are missing.",
                {"missing_columns": missing_columns},
            )
        )

    duplicate_count = int(panel.duplicated(["date", "code"]).sum()) if {"date", "code"}.issubset(panel.columns) else 0
    if duplicate_count:
        issues.append(
            DataQualityIssue(
                "blocker",
                "duplicates",
                "Duplicate date-code rows remain after normalization.",
                {"duplicate_count": duplicate_count},
            )
        )

    coverage: dict[str, float] = {}
    for column in required_columns:
        if column not in panel.columns:
            coverage[column] = 0.0
            continue
        coverage[column] = float(panel[column].notna().mean())
        if coverage[column] < min_required_coverage:
            issues.append(
                DataQualityIssue(
                    "blocker",
                    "coverage",
                    f"Required column {column} coverage is below threshold.",
                    {"coverage": coverage[column], "threshold": min_required_coverage},
                )
            )

    date_min = pd.to_datetime(panel["date"]).min() if "date" in panel.columns else pd.NaT
    date_max = pd.to_datetime(panel["date"]).max() if "date" in panel.columns else pd.NaT
    if pd.isna(date_min) or pd.isna(date_max):
        issues.append(DataQualityIssue("blocker", "date_range", "Panel has invalid dates."))
        date_min_str = ""
        date_max_str = ""
    else:
        date_min_str = date_min.strftime("%Y-%m-%d")
        date_max_str = date_max.strftime("%Y-%m-%d")
        if date_min.year < 2005:
            issues.append(
                DataQualityIssue(
                    "blocker",
                    "date_range",
                    "Earliest date is before 2005; this often indicates date parsing errors.",
                    {"date_min": date_min_str},
                )
            )

    if {"high", "low"}.issubset(panel.columns):
        bad_ohlc = int((panel["high"] < panel["low"]).sum())
        if bad_ohlc:
            issues.append(
                DataQualityIssue("blocker", "ohlc_bounds", "Rows where high < low exist.", {"count": bad_ohlc})
            )

    if "volume" in panel.columns:
        zero_volume_ratio = float((panel["volume"].fillna(0) <= 0).mean())
        if zero_volume_ratio > 0.20:
            issues.append(
                DataQualityIssue(
                    "warning",
                    "tradability",
                    "More than 20% of rows have non-positive volume.",
                    {"zero_volume_ratio": zero_volume_ratio},
                )
            )

    has_blocker = any(issue.severity == "blocker" for issue in issues)
    return DataQualityReport(
        source=source,
        status="failed" if has_blocker else ("warning" if issues else "passed"),
        row_count=int(len(panel)),
        date_min=date_min_str,
        date_max=date_max_str,
        n_codes=int(panel["code"].nunique()) if "code" in panel.columns else 0,
        duplicate_count=duplicate_count,
        coverage=coverage,
        issues=issues,
        diagnostics={
            "n_dates": int(panel["date"].nunique()) if "date" in panel.columns else 0,
            "columns": list(panel.columns),
        },
    )


def fetch_amazingdata_panel(
    *,
    start: str,
    end: str,
    universe: str = "csi800",
    symbols: Sequence[str] | None = None,
    max_symbols: int | None = 300,
    warmup_calendar_days: int = 420,
    min_symbol_coverage: float = 0.95,
    config: AmazingDataConfig | None = None,
    client: Any | None = None,
) -> tuple[pd.DataFrame, DataQualityReport]:
    cfg = config or AmazingDataConfig.from_env_file()
    active_client = client or create_client(cfg)
    output_start = pd.Timestamp(start).date()
    output_end = pd.Timestamp(end).date()
    query_start = output_start - timedelta(days=int(warmup_calendar_days))
    selected_symbols = list(symbols or [])
    if not selected_symbols:
        universe_symbols = resolve_amazingdata_universe_symbols(universe)
        selected_symbols = select_symbols(
            active_client,
            config=cfg,
            start_date=query_start,
            end_date=output_end,
            universe_symbols=universe_symbols,
            max_symbols=max_symbols,
            min_coverage=min_symbol_coverage,
        )
    if not selected_symbols:
        raise ValueError(f"No symbols selected for amazingdata universe={universe!r}")

    rows = active_client.execute(
        f"""
        SELECT
            trade_date AS date,
            symbol AS code,
            open,
            high,
            low,
            close,
            volume,
            amount
        FROM {_qualified(cfg, cfg.price_table)}
        WHERE symbol IN %(symbols)s
          AND trade_date BETWEEN %(start)s AND %(end)s
        ORDER BY symbol, trade_date
        """,
        {"symbols": tuple(selected_symbols), "start": query_start, "end": output_end},
    )
    raw = pd.DataFrame(rows, columns=["date", "code", "open", "high", "low", "close", "volume", "amount"])
    panel = normalize_price_panel(raw)
    report = build_data_quality_report(panel, source="amazingdata")
    return panel, report


def build_panel_snapshot(
    request: PanelRequest,
    quality: DataQualityReport,
    *,
    config: AmazingDataConfig | None = None,
    panel_path: str = "",
) -> PanelSnapshot:
    cfg = config or AmazingDataConfig.from_env_file()
    source = DataSourceSpec(
        name="amazingdata",
        kind="clickhouse",
        description="Read-only amazingdata ClickHouse market data.",
        config_path=str(DEFAULT_ENV_FILE),
        readonly=True,
        metadata=cfg.redacted(),
    )
    return PanelSnapshot(
        request=request,
        source=source,
        quality=quality,
        panel_path=panel_path,
        rows=quality.row_count,
        n_codes=quality.n_codes,
        n_dates=int(quality.diagnostics.get("n_dates", 0)),
    )
