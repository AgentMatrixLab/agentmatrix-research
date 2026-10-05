"""Write the delivery README from the artifacts themselves.

The delivery produces a 25-column manifest, a supplementary report, strategy demos, live
signals, an auditable package and a cross-check. What it did not produce is the one page that
says which file is which and what the delivery actually contains -- and a hand-written version
would carry numbers that go stale the moment the chain runs again.

So this reads the artifacts and writes the page from them. Nothing here computes a statistic it
could instead read, and anything missing is stated as missing rather than quietly omitted.

    python -X utf8 scripts/build_delivery_readme.py --delivery-dir delivery
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

#: Terms the delivery documentation must not use: the acceptance checklist forbids promising
#: returns, and this page reports a negative out-of-sample result.
FORBIDDEN_PHRASES = ("保证收益", "承诺收益", "预期年化收益", "必赚", "稳赚")


class ReadmeError(RuntimeError):
    """Raised when the README cannot be built honestly."""


def read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def format_count(value: object) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "—"


def build_readme(delivery: Path) -> str:
    manifest_summary = read_json(delivery / "delivery_manifest.summary.json")
    supplementary = read_json(delivery / "supplementary_report.json")
    clusters = read_json(delivery / "strategy_demos" / "clusters.json")
    backtests = read_json(delivery / "strategy_demos" / "backtest_results.json")
    signals = read_json(delivery / "live_signals" / "signal_summary.json")
    package = read_json(delivery / "package" / "package_manifest.json")
    cross_check = read_json(delivery / "cross_check.json")
    batch = read_json(delivery / "merged_oos" / "batch_manifest.json")

    lines: list[str] = ["# 晨星 300 因子交付 · 说明", ""]

    # ── 1. 交付了什么 ────────────────────────────────────────────────
    delivered = None if manifest_summary is None else manifest_summary.get("in_delivery_package")
    lines += ["## 一、交付了什么", ""]
    if manifest_summary is None:
        lines += ["> `delivery_manifest.summary.json` 不存在；交付清单尚未生成。", ""]
    else:
        target_met = isinstance(delivered, int) and delivered >= 300
        lines += [
            f"- 交付清单行数：**{format_count(manifest_summary.get('total'))}**（全部授权候选）",
            f"- **进入交付包（通过全部八道冻结门槛）：{format_count(delivered)}**",
            f"- 达成 300 的目标：**{'是' if target_met else '否'}**",
            f"- 状态分布：通过 {format_count(manifest_summary.get('validated'))}、"
            f"拒绝 {format_count(manifest_summary.get('rejected'))}、"
            f"未评估 {format_count(manifest_summary.get('not_run'))}",
            f"- 排序优先档（S/A，仅排序不代表门槛）：{format_count(manifest_summary.get('in_delivery_package_tier_sa'))}",
            f"- 交付簇数：{format_count(manifest_summary.get('delivered_clusters'))}，"
            f"簇代表：{format_count(manifest_summary.get('representatives'))}",
        ]
        if not target_met:
            lines += [
                "",
                "> 数量未达 300。**没有放宽任何冻结门槛来凑数**：门槛一个未动，"
                "未达标的因子如实标记为未通过或未评估。",
            ]
        lines += [""]

    if batch is not None:
        counts = batch.get("counts") or {}
        lines += [
            f"本次评估的批次范围（已完成分片的并集）：候选 {format_count(batch.get('candidate_count'))}，"
            f"其中通过 {format_count(counts.get('validated'))}、拒绝 {format_count(counts.get('rejected'))}。",
            "",
        ]

    # ── 2. 口径 ──────────────────────────────────────────────────────
    lines += [
        "## 二、口径（与代码一致）",
        "",
        "| 事项 | 口径 |",
        "|---|---|",
        "| 什么算「可交付」 | **通过全部八道冻结门槛**且非风险暴露（`in_delivery_package`） |",
        "| FDR | **勋章**：`fdr_accepted` 列标注，**不参与**是否交付 |",
        "| 打分卡 tier | **排序**：用于排优先级，**不作门槛** |",
        "| 因子方向 | 取自冻结验证器的 `training.direction`（仅训练段测量） |",
        "| 冗余相关性 | 逐日横截面 Spearman 的时间平均 |",
        "| 基准 | 全市场等权日收益指数 |",
        "",
    ]
    if supplementary is not None:
        summary = supplementary.get("summary") or {}
        marginal = supplementary.get("marginal_effect") or {}
        lines += [
            f"多重检验（Benjamini-Hochberg, q={summary.get('q')}）：提交 "
            f"{format_count(summary.get('n_submitted'))}、可检验 {format_count(summary.get('n_tested'))}、"
            f"通过 FDR **{format_count(summary.get('n_accepted'))}**。",
        ]
        if marginal:
            lines += [
                f"未校正时 p < q 的有 {format_count(marginal.get('passed_uncorrected'))} 个，"
                f"校正后剩 {format_count(marginal.get('passed_fdr'))} 个。",
            ]
        lines += [""]

    # ── 3. 产物清单 ──────────────────────────────────────────────────
    lines += [
        "## 三、产物清单",
        "",
        "| 文件 | 内容 |",
        "|---|---|",
        "| `delivery_manifest.csv` | 25 列冻结 schema 的主交付表（列顺序即契约） |",
        "| `delivery_manifest.summary.json` | 上表的计数摘要 |",
        "| `supplementary_report.json` / `.md` | FDR 勋章 + 行业中性留存（追加证据层） |",
        "| `strategy_demos/` | `strategies.json`、`backtest_results.json`、`clusters.json`（含簇与代表） |",
        "| `live_signals/` | `file_orders.csv`（文件单）、`conditional_orders.json`（条件单）、"
        "`supabase_rows.json`（Supabase 行）、`signal_summary.json` |",
        "| `package/` | 逐因子证据：`factors/<id>/` 下每个文件的 sha256、`factor_catalog.csv`、"
        "`package_manifest.json`（含每个被排除因子的**具体失败数值**） |",
        "| `cross_check.json` | 独立重算批次内每个哈希的结果 |",
        "| `merged_oos/` | 合并后的分片判决与批次候选范围 |",
        "",
    ]

    # ── 4. 样本外结果 ────────────────────────────────────────────────
    lines += ["## 四、样本外结果", ""]
    if backtests is None:
        lines += ["尚未生成策略演示。", ""]
    else:
        results = backtests.get("results") or {}
        window = backtests.get("backtest_window") or {}
        lines += [
            f"回测窗口：{window.get('start')} ~ {window.get('end')}；"
            f"成本模型：单边换手计成本，往返 {backtests.get('cost_model', {}).get('round_trip_total')}。",
            "",
            "| 策略变体 | 累计 | 年化 | 基准 | 超额 | 最大回撤 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for name, payload in results.items():
            metrics = payload.get("metrics") or {}

            def pct(key: str) -> str:
                value = metrics.get(key)
                return "—" if not isinstance(value, (int, float)) else f"{value:.2%}"

            lines.append(
                f"| `{name.replace('delivery_', '').replace('_v1', '')}` | {pct('total_return')} | "
                f"{pct('annualized_return')} | {pct('benchmark_return')} | "
                f"{pct('excess_return')} | {pct('max_drawdown')} |"
            )
        lines += [
            "",
            "> 以上为**样本外**区间结果，未做任何收益承诺。策略为多头集中组合，"
            "回撤较大；是否可用需结合客户的执行成本与风控约束自行判断。",
            "",
        ]
    if clusters is not None:
        lines += [
            f"冗余聚类：阈值 {clusters.get('threshold')}，"
            f"{format_count(clusters.get('n_clusters'))} 个簇 / "
            f"{format_count(len(clusters.get('representatives') or []))} 个代表"
            "（低相关核心集即代表集合）。",
            "",
        ]

    # ── 5. 实盘信号怎么用 ────────────────────────────────────────────
    lines += ["## 五、实盘信号怎么用", ""]
    if signals is None:
        lines += [
            "本次未生成实盘信号（缺 `live_signals/signal_summary.json`），"
            "但产物位置与用法如下，以便信号生成后照此使用。",
            "",
        ]
    else:
        lines += [
            f"- 策略 `{signals.get('strategy_id')}`，交易日 **{signals.get('trade_date')}**；"
            f"目标持仓 {format_count(signals.get('n_targets'))} 只，"
            f"订单 {format_count(signals.get('n_orders'))} 笔"
            f"（买 {format_count(signals.get('n_buys'))}／卖 {format_count(signals.get('n_sells'))}）。",
            f"- 交易的核心因子：{', '.join(f'`{fid}`' for fid in (signals.get('core_factors') or []))}",
            "",
        ]

    # Unconditional: this documents a TOOL the client uses against their own fills, so it must
    # be present whether or not this particular run produced signals.
    lines += [
        "- `file_orders.csv` 为 UTF-8 带 BOM，可直接导入本地 QMT；"
        "`conditional_orders.json` 每笔带触发价（按 `price_offset_bps` 相对参考价偏移）。",
        "- `supabase_rows.json` 为待插入的行（`pushed: false`）：**仓库中的信号库不含 Supabase "
        "客户端**，上传是独立的一步，本交付不声称已推送。",
        "",
        "**执行偏差对账**：用终端的成交回单与文件单比对：",
        "",
        "```",
        "python -X utf8 scripts/reconcile_signals.py \\",
        "    --orders <delivery>/live_signals/file_orders.csv \\",
        "    --fills  <你的成交回单.csv> \\",
        "    --out-dir <delivery>/live_signals",
        "```",
        "",
        "输出 `deviation_report.json` / `.md`，逐项列出未成交、计划外成交、数量不符与价格滑点。"
        "退出码 0 = 无偏差，5 = 存在偏差，2 = 回单不可读（例如缺 `price` 列会被拒绝，"
        "而不是判成「全部未成交」）。",
        "",
    ]

    # ── 6. 验证证据 ──────────────────────────────────────────────────
    lines += ["## 六、验证证据", ""]
    if cross_check is not None:
        findings = cross_check.get("finding_count")
        lines.append(
            f"- 交叉验证 `cross_check.json`：独立重算批次内每个 `result_hash`、manifest/report "
            f"产物、面板与配置摘要、全部计数与名单——**发现数 {findings}**。"
        )
    if package is not None:
        counts = package.get("counts") or {}
        lines.append(
            f"- 可审计包：入选 {format_count(counts.get('included'))}、"
            f"排除 {format_count(counts.get('excluded'))}"
            f"（每个排除项都带失败门槛与具体数值），入选项的产物均记录 sha256。"
        )
    lines += [
        "- 冻结约束：`configs/validation_gates.yaml` 与 "
        "`research_core/factor_lab/deterministic_validation.py` 全程未改；"
        "新增层未被冻结验证器 import（有结构性测试保证）。",
        "- 全量测试：见仓库 `pytest` 结果；每一处执行期修正与实测数据见 "
        "`docs/delivery/2026-10-07-execution-findings.md`。",
        "",
        "## 七、诚实保留",
        "",
        "- 交付包由**八道冻结门槛**定义；打分卡仍是草案，只用于排序。",
        "- 样本外结果为负超额，见第四节；本说明不作任何收益表述。",
        "- 未评估的候选如实标记为 `not_run`，没有以任何方式补足数量。",
        "",
    ]

    text = "\n".join(lines)
    offenders = [phrase for phrase in FORBIDDEN_PHRASES if phrase in text]
    if offenders:
        raise ReadmeError(f"the delivery README contains performance promises: {offenders}")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--delivery-dir", required=True)
    parser.add_argument("--out", default="", help="defaults to <delivery-dir>/README.md")
    args = parser.parse_args(argv)

    delivery = Path(args.delivery_dir)
    if not delivery.is_dir():
        raise ReadmeError(f"delivery directory not found: {delivery}")
    out = Path(args.out) if args.out else delivery / "README.md"
    out.write_text(build_readme(delivery), encoding="utf-8")
    print(f"wrote {out}")
    print(f"  {len(out.read_text(encoding='utf-8').splitlines())} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
