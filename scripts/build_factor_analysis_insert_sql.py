from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Iterable


def quote_sql(value: object) -> str:
    if value is None:
        return "null"
    text = str(value)
    return "'" + text.replace("'", "''") + "'"


def quote_json(value: object) -> str:
    return quote_sql(json.dumps(clean_json(value), ensure_ascii=False, allow_nan=False)) + "::jsonb"


def clean_json(value: object) -> object:
    if isinstance(value, dict):
        return {key: clean_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_json(item) for item in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def number_or_null(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "null"
    if math.isnan(number) or math.isinf(number):
        return "null"
    return repr(number)


def int_or_null(value: object) -> str:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "null"
    return str(number)


def date_only(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text:
        return None
    if len(text) >= 10:
        return text[:10]
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError:
        return None


def parse_date(value: object) -> datetime | None:
    text = date_only(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def shift_years(value: datetime, years: int) -> datetime:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year + years)


def filter_daily_series(
    daily_series: list[object],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    last_years: int | None = None,
) -> list[tuple[int, dict[str, object]]]:
    dated_items: list[tuple[int, dict[str, object], datetime]] = []
    for index, item in enumerate(daily_series):
        if not isinstance(item, dict):
            continue
        trade_date = parse_date(item.get("date"))
        if not trade_date:
            continue
        dated_items.append((index, item, trade_date))

    if not dated_items:
        return []

    resolved_end = parse_date(end_date) or max(item[2] for item in dated_items)
    resolved_start = parse_date(start_date)
    if resolved_start is None and last_years:
        resolved_start = shift_years(resolved_end, -last_years)

    filtered = []
    for source_index, item, trade_date in dated_items:
        if resolved_start and trade_date < resolved_start:
            continue
        if resolved_end and trade_date > resolved_end:
            continue
        filtered.append((source_index, item))
    return filtered


def chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def cumulative_returns(items: list[dict[str, object]], key: str) -> list[float | None]:
    nav = 1.0
    values: list[float | None] = []
    for item in items:
        value = item.get(key)
        try:
            number = float(value)
        except (TypeError, ValueError):
            values.append(None)
            continue
        if math.isnan(number) or math.isinf(number):
            values.append(None)
            continue
        nav *= 1.0 + number
        values.append(nav)
    return values


def build_sql(
    meta: dict[str, object],
    chart: dict[str, object],
    chunk_size: int,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    last_years: int | None = None,
) -> str:
    factor_name = str(chart.get("factor_name") or meta.get("factor_name") or "").strip()
    library = str(chart.get("library") or meta.get("library") or meta.get("factor_set") or "unknown").strip()
    factor_family = meta.get("factor_set") or chart.get("factor_set")
    source_version = str(meta.get("version") or chart.get("version") or "v1")
    data_source = chart.get("data_source") or meta.get("data_source")
    config_hash = str(meta.get("config_hash") or chart.get("config_hash") or "default").strip()
    generated_at = chart.get("generated_at") or meta.get("created_at")
    dataset = chart.get("dataset") or {}
    metrics = chart.get("metrics") or {}
    ic_summary = chart.get("ic_summary") or {}
    group_returns = chart.get("group_returns") or {}
    long_short = chart.get("long_short") or {}
    monotonicity = chart.get("monotonicity") or {}
    daily_series = chart.get("daily_series") if isinstance(chart.get("daily_series"), list) else []
    filtered_daily_series = filter_daily_series(
        daily_series,
        start_date=start_date,
        end_date=end_date,
        last_years=last_years,
    )
    summary_dataset = dict(dataset) if isinstance(dataset, dict) else {}
    if filtered_daily_series:
        first_date = date_only(filtered_daily_series[0][1].get("date"))
        last_date = date_only(filtered_daily_series[-1][1].get("date"))
        summary_dataset.update(
            {
                "display_start_date": first_date,
                "display_end_date": last_date,
                "display_n_dates": len(filtered_daily_series),
            }
        )

    sql_parts = [
        "-- Generated by scripts/build_factor_analysis_insert_sql.py",
        "-- Run supabase/factor_analysis_results.sql before this file.",
        "begin;",
        f"""
insert into public.factor_analysis_results (
  factor_id,
  factor_name,
  library,
  factor_family,
  source_version,
  data_source,
  config_hash,
  n_groups,
  n_symbols,
  n_dates,
  dataset,
  metrics,
  ic_summary,
  group_returns_summary,
  long_short_summary,
  monotonicity,
  generated_at
) values (
  {quote_sql(factor_name)},
  {quote_sql(factor_name)},
  {quote_sql(library)},
  {quote_sql(factor_family)},
  {quote_sql(source_version)},
  {quote_sql(data_source)},
  {quote_sql(config_hash)},
  {int_or_null(chart.get("n_groups") or meta.get("n_groups"))},
  {int_or_null(meta.get("n_symbols") or dataset.get("n_stocks"))},
  {int_or_null(len(filtered_daily_series) or meta.get("n_dates") or dataset.get("n_dates"))},
  {quote_json(summary_dataset)},
  {quote_json(metrics)},
  {quote_json(ic_summary)},
  {quote_json(group_returns)},
  {quote_json(long_short)},
  {quote_json(monotonicity)},
  {quote_sql(generated_at)}::timestamptz
)
on conflict (factor_name, library, config_hash) do update set
  factor_id = excluded.factor_id,
  factor_family = excluded.factor_family,
  source_version = excluded.source_version,
  data_source = excluded.data_source,
  n_groups = excluded.n_groups,
  n_symbols = excluded.n_symbols,
  n_dates = excluded.n_dates,
  dataset = excluded.dataset,
  metrics = excluded.metrics,
  ic_summary = excluded.ic_summary,
  group_returns_summary = excluded.group_returns_summary,
  long_short_summary = excluded.long_short_summary,
  monotonicity = excluded.monotonicity,
  generated_at = excluded.generated_at,
  created_at = now();
""".strip(),
        f"delete from public.factor_analysis_ic_series where factor_name = {quote_sql(factor_name)} and library = {quote_sql(library)} and config_hash = {quote_sql(config_hash)};",
        f"delete from public.factor_analysis_group_series where factor_name = {quote_sql(factor_name)} and library = {quote_sql(library)} and config_hash = {quote_sql(config_hash)};",
    ]

    ic_values: list[str] = []
    for _, item in filtered_daily_series:
        trade_date = date_only(item.get("date"))
        if not trade_date:
            continue
        ic_values.append(
            "("
            f"{quote_sql(factor_name)}, {quote_sql(library)}, {quote_sql(config_hash)}, "
            f"{quote_sql(trade_date)}::date, {number_or_null(item.get('rank_ic'))}, "
            f"{number_or_null(item.get('pearson_ic'))}, {int_or_null(item.get('n_stocks'))}"
            ")"
        )

    for chunk in chunks(ic_values, chunk_size):
        sql_parts.append(
            "insert into public.factor_analysis_ic_series "
            "(factor_name, library, config_hash, trade_date, rank_ic, pearson_ic, n_stocks) values\n"
            + ",\n".join(chunk)
            + "\non conflict (factor_name, library, config_hash, trade_date) do update set "
            "rank_ic = excluded.rank_ic, pearson_ic = excluded.pearson_ic, n_stocks = excluded.n_stocks;"
        )

    group_values: list[str] = []
    filtered_items = [item for _, item in filtered_daily_series]
    long_short_nav = cumulative_returns(filtered_items, "long_short")
    group_nav_state: dict[str, float] = {}
    for index, item in enumerate(filtered_items):
        trade_date = date_only(item.get("date"))
        if not trade_date:
            continue
        groups = item.get("groups") if isinstance(item.get("groups"), dict) else {}
        for group_key, group_return in groups.items():
            group_no = int_or_null(group_key)
            series_key = f"G{group_key}"
            try:
                return_number = float(group_return)
            except (TypeError, ValueError):
                return_number = math.nan
            if not math.isnan(return_number) and not math.isinf(return_number):
                group_nav_state[str(group_key)] = group_nav_state.get(str(group_key), 1.0) * (1.0 + return_number)
                nav_value: float | None = group_nav_state[str(group_key)]
            else:
                nav_value = None
            group_values.append(
                "("
                f"{quote_sql(factor_name)}, {quote_sql(library)}, {quote_sql(config_hash)}, "
                f"{quote_sql(trade_date)}::date, {quote_sql(series_key)}, 'group', {group_no}, "
                f"{number_or_null(group_return)}, {number_or_null(nav_value)}"
                ")"
            )
        if "long_short" in item:
            group_values.append(
                "("
                f"{quote_sql(factor_name)}, {quote_sql(library)}, {quote_sql(config_hash)}, "
                f"{quote_sql(trade_date)}::date, 'LS', 'long_short', null, "
                f"{number_or_null(item.get('long_short'))}, {number_or_null(long_short_nav[index] if index < len(long_short_nav) else None)}"
                ")"
            )

    for chunk in chunks(group_values, chunk_size):
        sql_parts.append(
            "insert into public.factor_analysis_group_series "
            "(factor_name, library, config_hash, trade_date, series_key, series_type, group_no, group_return, group_nav) values\n"
            + ",\n".join(chunk)
            + "\non conflict (factor_name, library, config_hash, trade_date, series_key) do update set "
            "series_type = excluded.series_type, group_no = excluded.group_no, "
            "group_return = excluded.group_return, group_nav = excluded.group_nav;"
        )

    sql_parts.append("commit;")
    return "\n\n".join(sql_parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build normalized Supabase SQL from meta + stratification JSON.")
    parser.add_argument("--meta", required=True, help="Path to meta.json.")
    parser.add_argument("--chart", required=True, help="Path to stratification.json.")
    parser.add_argument("--out", required=True, help="Output SQL path.")
    parser.add_argument("--chunk-size", type=int, default=500, help="Rows per INSERT statement.")
    parser.add_argument("--start-date", help="Inclusive start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", help="Inclusive end date, YYYY-MM-DD. Defaults to latest date in chart.")
    parser.add_argument("--last-years", type=int, help="Keep only the last N calendar years before end date.")
    args = parser.parse_args()

    meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))
    chart = json.loads(Path(args.chart).read_text(encoding="utf-8"))
    sql = build_sql(
        meta,
        clean_json(chart),
        max(1, args.chunk_size),
        start_date=args.start_date,
        end_date=args.end_date,
        last_years=args.last_years,
    )
    Path(args.out).write_text(sql, encoding="utf-8")


if __name__ == "__main__":
    main()
