"""
轻量任务队列 — 基于 SQLite，无外部依赖

内存/CPU 保护:
  - 同一时间最多 1 个回测 Worker（MAX_CONCURRENT_BACKTESTS=1）
  - progress 由引擎 on_progress 回调驱动，非 polling
  - 完成后立即释放引擎内存
"""
import threading
import time
import uuid
import json
from datetime import datetime
from config import MAX_CONCURRENT_BACKTESTS

_job_lock = threading.Lock()
_active_jobs = 0


def submit_job(db_factory, source_code: str, strategy_name: str, file_name: str, params: dict) -> str:
    """提交回测任务，返回 job_id"""
    job_id = f"BT-{datetime.now().strftime('%y%m%d')}-{uuid.uuid4().hex[:3].upper()}"
    db = db_factory()
    db.execute(
        """INSERT INTO backtest_jobs (id, strategy_name, status, progress, file_name, params)
           VALUES (?,?,?,?,?,?)""",
        [job_id, strategy_name, "queued", 0, file_name, json.dumps(params)]
    )
    db.commit()
    db.close()

    # 启动 Worker
    t = threading.Thread(target=_worker, args=(db_factory, job_id, source_code, params), daemon=True)
    t.start()
    return job_id


def _worker(db_factory, job_id: str, source_code: str, params_dict: dict):
    global _active_jobs, _job_lock

    # 并发控制：排队等待
    while True:
        with _job_lock:
            if _active_jobs < MAX_CONCURRENT_BACKTESTS:
                _active_jobs += 1
                break
        time.sleep(0.5)

    try:
        db = db_factory()
        db.execute("UPDATE backtest_jobs SET status='running' WHERE id=?", [job_id])
        db.commit()
        db.close()

        from engine_adapter import run, Params
        params = Params(**params_dict)

        def on_progress(pct):
            db2 = db_factory()
            db2.execute("UPDATE backtest_jobs SET progress=? WHERE id=?", [pct, job_id])
            db2.commit()
            db2.close()

        start = time.time()
        result = run(source_code, params, on_progress=on_progress)
        elapsed = int((time.time() - start) * 1000)

        # 写入结果至 DB
        db = db_factory()
        result_id = f"RES-{job_id}"
        db.execute(
            "UPDATE backtest_jobs SET status='done', progress=100, result_id=?, duration_ms=?, completed_at=? WHERE id=?",
            [result_id, elapsed, datetime.now().isoformat(), job_id]
        )

        # 结果合并到 params 中（单 JSON 对象，禁止拼接）
        result_data = {
            "nav": result.nav,
            "kpis": result.kpis,
            "holdings": result.holdings,
            "trades": result.trades,
        }
        current_params = json.loads(db.execute(
            "SELECT params FROM backtest_jobs WHERE id=?", [job_id]
        ).fetchone()["params"])
        current_params["result"] = result_data
        db.execute(
            "UPDATE backtest_jobs SET params=? WHERE id=?",
            [json.dumps(current_params, ensure_ascii=False), job_id]
        )
        db.commit()
        db.close()

    except Exception as e:
        db = db_factory()
        db.execute(
            "UPDATE backtest_jobs SET status='failed', error=?, completed_at=? WHERE id=?",
            [str(e)[:500], datetime.now().isoformat(), job_id]
        )
        db.commit()
        db.close()
    finally:
        with _job_lock:
            _active_jobs -= 1
