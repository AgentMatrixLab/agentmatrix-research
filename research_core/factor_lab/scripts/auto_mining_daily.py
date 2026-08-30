"""每日自动因子挖掘 — cron 调度入口.

用法 (手动):
    PYTHONPATH=. python research_core/factor_lab/scripts/auto_mining_daily.py

用法 (cron, 每交易日 19:30):
    30 19 * * 1-5 cd <repo_root> && /usr/bin/env python \
        research_core/factor_lab/scripts/auto_mining_daily.py >> runtime/mining_runs/cron.log 2>&1

流程:
    1. 加载 .env.local 中的 FACTOR_LAB_QUANT_API_TOKEN (有则 API 拉最新面板)
    2. GP 搜索 (默认) + 内置候选基线, 真实 IC 评估 + 去重
    3. 结果落盘 runtime/mining_runs/
    4. 面板缓存到 runtime/mining_cache/ 供次日复用
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from research_core.factor_lab.auto_mining import (  # noqa: E402
    load_panel,
    run_mining_loop,
    save_results,
)
from research_core.factor_lab.real_data import load_local_env  # noqa: E402
from research_core.factor_lab.runtime import now_iso  # noqa: E402

THEME = "量价因子: 动量/反转/波动率/量价背离"
ROUNDS = 2
GP_POPULATION = 24
GP_GENERATIONS = 5


def main() -> int:
    print(f"[{now_iso()}] auto_mining_daily start")
    try:
        # 1. Panel: API (token) → cache → synthetic
        #    仅在配置了 token 时刷新缓存, 避免 token 失效后悄悄退化到合成数据
        import os

        load_local_env()
        has_token = bool(os.getenv("FACTOR_LAB_QUANT_API_TOKEN") or os.getenv("QUANT_API_TOKEN"))
        panel, source = load_panel(source="auto", refresh_cache=has_token)
        if source == "synthetic":
            print(f"[{now_iso()}] WARNING: no real data (token missing & no cache) — "
                  "synthetic panel is for pipeline self-check only")
        print(f"[{now_iso()}] panel loaded: {panel.shape}, source={source}")

        # 2. GP search
        from research_core.factor_lab.gp_search import GPFactorMiner

        miner = GPFactorMiner(panel)
        gp_out = miner.evolve(generations=GP_GENERATIONS, population=GP_POPULATION)
        print(f"[{now_iso()}] GP done: {gp_out['evaluations']} evaluations")

        # 3. Baseline + LLM loop (LLM 自动降级 builtin)
        loop_out = run_mining_loop(panel, theme=THEME, rounds=ROUNDS, mode="auto")

        # 4. Persist
        run_output = {
            "rounds": loop_out["rounds"],
            "winners": loop_out["winners"] + gp_out["winners"],
            "all_results": loop_out["all_results"] + list(miner.cache.values()),
        }
        csv_path = save_results(run_output, panel_source=source)
        print(f"[{now_iso()}] saved: {csv_path}")
        print(f"[{now_iso()}] winners: {[r.name for r in run_output['winners']]}")
        return 0
    except Exception:
        print(f"[{now_iso()}] FAILED:\n{traceback.format_exc()}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
