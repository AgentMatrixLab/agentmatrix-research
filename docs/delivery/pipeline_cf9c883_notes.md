# cf9c883 正式验证流水线阅读笔记（只读，不改代码）

对象：`origin/server/pipeline-cf9c883`，commit `cf9c8836c2aca390a9a6e6a17550ce4af981d7b4`（作者 `AgentMatrix Automation`，2026-09-25）。
基线：`61dcf19`（= `origin/main` 当时的 HEAD），该分支相对 main 只领先这 1 个 commit。
本文所有行号均指 **cf9c883 版本的 `research_core/factor_lab/deterministic_validation.py`（共 979 行）**，不是交付分支上的版本。

## 1. 入口命令

唯一正式入口是 `factor_lab` CLI 的 `validate` 子命令：

```bash
python -m research_core.factor_lab.cli validate --factor reversal_1m --config configs/validation_gates.yaml
```

- 参数定义：`research_core/factor_lab/cli.py` 第 201-210 行（`--factor` 必填，`--config` 默认 `configs/validation_gates.yaml`）。
- 执行体：`cli.py` 第 467-474 行，调用 `execute_validation(args.factor, config_path=args.config)`，把返回的 dict 打到 stdout。
- Makefile 里包了一层：`make validate FACTOR=reversal_1m`（`VALIDATION_CONFIG` 可覆盖 config 路径）。
- **退出码**：只有 `status == "needs_human"` 才 `SystemExit(2)`；因子被 `rejected` 时退出码仍是 **0**。批量脚本必须读 `validation_result.json` 的 `status`，不能靠退出码。
- `--factor` 必须是 config 里 `factor.definitions` 已登记的因子 ID，否则 `_rolling_factor` 抛 `Unsupported deterministic factor`（第 356-357 行）。

## 2. 数据从哪来（两条路）

`execute_validation`（第 917-951 行）分两条：

1. **联网路（默认）**：`panel is None` → `RQDataPanelLoader(config).load(factor_id)`（第 934 行）。
   走 `rqdatac.init()` + `get_price` / `get_shares` / `is_st_stock` / `is_suspended` / `get_turnover_rate`（第 181-280 行），分 `batch_size=300` 批拉全 A。
   结果 pickle 缓存到 `data/factor_lab/validation_cache/<request_sha256>.pkl`（第 176-179 行，`cache_enabled: true`）。缓存键 = `sha256(canonical_json(request))`，request 含 provider/universe/frequency/adjust_type/warmup_start/validation_end/price_fields/limit_*/turnover_field/shares_field/**factor_id**（第 162-176 行）。
   注意：**缓存键里带 factor_id**，不同因子不会共用缓存。
2. **离线/喂数路**：`panel is not None` → 直接用传入的 DataFrame，`source_metadata` 缺省为 `{"provider": "provided_panel"}`（第 931-935 行）。
   **这是本地离线跑和 D2「预计算因子」要走的接入口**，可以完全绕开 rqdatac 联网。

## 3. 因子在哪一步算（关键）

都在 `validate_panel`（第 629 行起）里，顺序是：

1. 第 659 行 `clean = _eligible_panel(panel, config)` —— 先做全 A 可交易过滤：
   上市满 `minimum_listing_days=120` 天、未退市、非 ST、非停牌、`volume > 0`、`listed_date` 非空、`close` 严格小于涨停价且大于跌停价（第 310-351 行）。
2. **第 660-666 行 = 因子值唯一注入点**：
   - `transform == "negative_pct_change"`（当前只有 `reversal_1m`）→ `clean["factor_value"] = _map_factor_values(clean, _factor_lookup(panel, selected_factor, config))`
     - `_factor_lookup`（第 408-419 行）在**未过滤的整块 panel** 上算因子，返回以 `(date, code)` 为 MultiIndex 的 Series；
     - `_map_factor_values`（第 422-432 行）再按 `(date, code)` 映回过滤后的 `clean`。
     - 绕这一圈的原因：`negative_pct_change` 要求 T-22 是**连续交易日**、且窗口内每天都 `is_suspended == False` 且价格 > 0（第 364-397 行），所以必须在过滤前的全 panel 上按交易日位置推，不能在 `clean` 上直接 rolling。
   - 其他 transform（`rolling_mean` / `rolling_mean_log`）→ `clean["factor_value"] = _rolling_factor(clean, selected_factor, config)`。
   - 不支持的 transform 直接 `ValueError`（第 404 行）。
3. 第 667 行 `_build_styles` —— size / momentum(252) / volatility(60) / liquidity(20)。
4. 第 669 行 `_attach_forward_returns` —— horizons `[5, 10, 20]`。
5. 第 671-672 行 `_bounded_period` 切 train / oos。

**结论：要换成「读预计算因子」，只需要改第 660-666 行这一段，后面的切分、门槛、组合、扰动一行都不用碰。**

## 4. 门槛在哪个文件、哪一步判定

- **阈值全在 `configs/validation_gates.yaml` 的 `gates:` 段**（cf9c883 版本第 114-136 行），判定顺序 `gates.order`：
  `coverage → rank_ic → oos_seal → style_r2 → residual_ic → cost_adjusted_return → dd_vol_ratio → parameter_perturbation`。
- **判定代码在 `validate_panel` 第 760-833 行**：每条用 `_gate(name, passed, actual, threshold)`（第 625 行）包成 `{name, passed, actual, threshold}`；第 832-833 行 `status = "rejected" if failed else "validated"`。
- 冻结阈值（不许改）：
  | gate | 阈值 |
  |---|---|
  | coverage | `minimum_daily_ratio: 0.95` |
  | rank_ic | `minimum_abs_mean: 0.01` 且 `minimum_abs_t_stat: 1.65` |
  | style_r2 | `maximum_mean: 0.80` |
  | residual_ic | `minimum_retention: 0.50`（且残差 IC 与原始 IC 同号） |
  | cost_adjusted_return | `minimum_annualized: 0.0`（注意是严格大于） |
  | dd_vol_ratio | `maximum: 3.0` |
  | parameter_perturbation | 扰动窗口 ×0.8 / ×1.2 后 RankIC 符号必须与基准一致 |
  | oos_seal | 不是阈值，是切分自检：train 最大日期 ≤ `train_end`、oos 最小日期 ≥ `oos_start`、train 标签最大 `target_date` ≤ `train_end`（第 763-769 行） |
- 成本参数在 `portfolio.cost`（第 103-107 行）：`commission_per_side 0.00015`、`stamp_tax_sell 0.001`、`impact_per_side 0.00085`、`round_trip_total 0.003`。
  第 644-651 行会校验「分项之和 == round_trip_total」（容差 `statistics.numeric_tolerance = 1e-12`），不等直接 `ValueError` —— 所以成本既不能只改一个分项，也不能只改 total。
- 切分在 `split:`（第 35-39 行）；统计口径在 `statistics:`（`minimum_ic_cross_section: 20`、`ddof: 1`、`numeric_tolerance: 1e-12`）。
- 入库门槛前置检查：`release.mode == external_mode` 且 `license_checked == false` 时直接 `MissingDataError`（第 636-641 行）。当前 `mode: internal_preview`，所以走得通。

## 5. 输出哪些文件、哪些 hash

输出根 = `output.root`（`data/factor_lab/validation_runs`），每个因子一个子目录 `<root>/<factor_id>/`（第 107-116 行）：

| 文件 | 内容 |
|---|---|
| `validation_report.md` | 人读：首行 `status=... failed_gate=...`，gate 表（name/status/actual/threshold），RankIC 表（mean/IC_IR/t-stat/days） |
| `validation_result.json` | 机器读，`float_precision: 12`；含 `status`、`requested_factor`、`factor_id`、`fallback_reason`、`gates[]`、`failed_gates[]`、`rank_ic{}`、`style{}`、`portfolio{}`、`perturbation{}`、`training{direction, primary_rank_ic_mean}`、`data{eligible_rows, eligible_codes, eligible_dates}` |
| `run_manifest.json` | 见下 |
| `needs_human.json` | 只在 `MissingDataError` 时写；每次运行开头会先删掉旧的（第 927-928 行） |

`run_manifest.json`（第 956-965 行）字段：

- `data_snapshot_hash` = `_frame_hash(panel)` —— 对**传入的原始 panel**（未过滤）按 `(date, code)` 排序后算：列名+dtypes 的 canonical json 拼上逐行 hash 的 sha256（第 85-94 行）。
- `code_commit` = 在 `PROJECT_ROOT` 跑 `git rev-parse HEAD`（第 97-104 行）。**注意这是运行目录的 HEAD，不是被测代码写死的版本。**
- `params_hash` = `sha256(canonical_json({"factor_id": ..., "config": 整个 yaml}))` —— config 一改，hash 必变。
- `result_hash` = `sha256(canonical_json(result_safe))`（precision=12 之后）。
- `constraints_file` / `constraints_sha256` = 仓库根有 `constraints-rqsdk.txt` 时记录（第 962-965 行）。该文件由 cf9c883 新增。

## 6. 在哪里能接入「预计算因子」而不碰门槛

**唯一注入点：`validate_panel` 第 660-666 行。** 具体做法（D2 实现方向）：

1. 新增一个「因子来源」开关（例如 `--factor-file <parquet>` + sidecar sha256），在进入第 660 行之前把预计算值读成以 `(date, code)` 为键的 Series。
2. 用同一套 `_map_factor_values(clean, values)` 把它映射到 `clean["factor_value"]`，**不调用** `_rolling_factor` / `_factor_lookup`。
3. 切分、`_eligible_panel`、`_build_styles`、`_attach_forward_returns`、`_gate`、`gates.order`、`status` 判定、成本参数——**全部保持原样，一行不改**。
4. `oos_seal`、`coverage`、`rank_ic` 等门槛因此自动复用同一套代码，等价性天然成立。

**必须提前说清楚的一个坑**：扰动窗口那一段（第 738-758 行）会**重算** `perturbed_factor`，用的是 `_rolling_factor(..., window = round(base_window × 0.8/1.2))`。因子来自预计算文件时没有「换窗口重算」的能力，所以：

- 可选方案 A：预计算文件里同时提供 0.8× / 1.2× 窗口的因子列；
- 可选方案 B：该因子 `parameter_perturbation` 如实标记为「无法测量」并计入未通过/待人工。
- **绝不允许**让这条 gate 悄悄变成恒真（那就是变相降门槛）。这件事需要 Sam/Patric 定，我在 D2 里会按「不静默放行」的原则实现，并在 runbook 里写明。

## 7. 边界与已知坑（供 D2/D3 参考）

1. **列名不兼容**：`RQDataPanelLoader` 需要 RQData 原生列名 `listed_date` / `de_listed_date` / `total_turnover` / `circulation_a` / `is_suspended` / `is_st` / `turnover_rate`；Trae 的数据契约用的是 `listing_date` / `delisting_date` / `amount` / `adjustment_factor`。**离线喂真实面板需要一层列名适配**，不能直接塞。
2. **复权口径冲突**：config 写 `adjust_type: post`（用后复权价），Trae 契约写「原始未复权 OHLC + 独立复权因子」。两者对不上，跑之前必须定口径。
3. **切分冲突（已取证）**：config 是 train `2016-01-01~2023-12-31` / OOS `2024-01-01~2026-08-31`；任务书冻结的是 train 到 `2022-12-31` / OOS 从 `2023-01-01` 起。**没有 Sam 确认前我不动 config。**
   取证结果（`2026-10-03`）：
   - `git log --follow -- configs/validation_gates.yaml` 只有两个 commit：`61dcf19`（建文件，PR #120）与 `cf9c883`（只加了 `reversal_1m` 定义）。
   - `git log -S'train_end'` 与 `git log -S'adjust_type'` 都只命中 `61dcf19` —— 也就是说**这个切分和 `adjust_type: post` 自建库起从未变过**。
   - 全仓 `grep 2022-12-31` **零命中**（`*.md`、`*.py`、`*.yaml` 都没有）。任务书里的冻结切分在仓库里**没有任何对应记录**。
   - 没有任何测试把这个生产切分写死（`tests/` 里只有 `conftest.py` 自己合成面板用的 `2017-12-31/2018-01-01`）。**因此改 config 的切分不会破坏任何测试**，这纯粹是一个口径决定，不是技术约束。
   - 结论：两个日期都「有出处」——一个是代码事实（`61dcf19`），一个只存在于任务书。**必须由 Sam 裁定后改 config，或由 Sam 确认以 config 为准并修正任务书。**
4. **自动 fallback**：`factor.primary = turnover_20d`，若 panel 缺 `turnover_rate` 列，会自动换成 `avg_amount_log` 并写 `fallback_reason`（第 655-657 行）。批量跑时不能把 fallback 结果当成原因子结果。
5. **硬性数据要求**：`_eligible_panel` 要求 `limit_up` / `limit_down` 非空，且 `close` 严格落在两者之间；缺字段抛 `MissingDataError` 并写 `needs_human.json`。
6. **rejected 不报错**：退出码仍为 0，批量驱动必须读 JSON。
7. `_frame_hash` 的输入是**未过滤的原始 panel**，所以「面板 hash」对同一次导出的同一份面板是稳定的；换了列顺序/结构就会变。

## 8. 我这次做了什么 / 没做什么

- 只做了：`git show cf9c883`、读上述三个文件、`merge-tree` 预检冲突。
- 没做：没有 checkout 到该分支、没有修改任何代码、没有运行流水线（本机没有 RQData 数据，也不该联网跑）。
- 本文不构成任何因子有效性证据。
