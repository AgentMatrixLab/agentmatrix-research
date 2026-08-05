"""
SQLite 数据层 — 使用标准库 sqlite3（零依赖）
WAL 模式 + 预编译语句，内存占用可控
"""
import sqlite3
import os
import json
from pathlib import Path
from config import DB_PATH, DB_PAGE_SIZE, DB_CACHE_SIZE_MB


def get_db() -> sqlite3.Connection:
    """获取数据库连接（每线程一个，复用）"""
    db = sqlite3.connect(DB_PATH, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(f"PRAGMA page_size={DB_PAGE_SIZE}")
    db.execute(f"PRAGMA cache_size={int(DB_CACHE_SIZE_MB * 256)}")  # KB
    db.execute("PRAGMA mmap_size=67108864")  # 64MB mmap
    db.execute("PRAGMA temp_store=MEMORY")
    db.execute("PRAGMA busy_timeout=5000")
    return db


def init_db():
    """建表 + 灌入种子数据"""
    Path(os.path.dirname(DB_PATH)).mkdir(parents=True, exist_ok=True)
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS strategies (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            tag TEXT DEFAULT '',
            status TEXT DEFAULT 'running',
            version TEXT DEFAULT 'v1.0',
            created_at TEXT DEFAULT (datetime('now')),
            source_code TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS nav_series (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id TEXT NOT NULL,
            date TEXT NOT NULL,
            nav REAL NOT NULL,
            benchmark_nav REAL DEFAULT 1.0,
            drawdown REAL DEFAULT 0.0,
            UNIQUE(strategy_id, date)
        );
        CREATE INDEX IF NOT EXISTS idx_nav_sid_date ON nav_series(strategy_id, date);

        CREATE TABLE IF NOT EXISTS kpis (
            strategy_id TEXT PRIMARY KEY,
            total_return REAL DEFAULT 0,
            annual_return REAL DEFAULT 0,
            sharpe REAL DEFAULT 0,
            max_drawdown REAL DEFAULT 0,
            win_rate REAL DEFAULT 0,
            volatility REAL DEFAULT 0,
            alpha REAL DEFAULT 0,
            beta REAL DEFAULT 0,
            sortino REAL DEFAULT 0,
            calmar REAL DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            industry TEXT DEFAULT '',
            qty REAL DEFAULT 0,
            cost REAL DEFAULT 0,
            price REAL DEFAULT 0,
            value REAL DEFAULT 0,
            pnl REAL DEFAULT 0,
            pnl_pct REAL DEFAULT 0,
            weight REAL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_holdings_sid ON holdings(strategy_id);

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id TEXT NOT NULL,
            time TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            side TEXT NOT NULL,
            price REAL DEFAULT 0,
            qty REAL DEFAULT 0,
            amount REAL DEFAULT 0,
            fee REAL DEFAULT 0,
            FOREIGN KEY(strategy_id) REFERENCES strategies(id)
        );
        CREATE INDEX IF NOT EXISTS idx_trades_sid_time ON trades(strategy_id, time DESC);

        CREATE TABLE IF NOT EXISTS backtest_jobs (
            id TEXT PRIMARY KEY,
            strategy_name TEXT DEFAULT '',
            status TEXT DEFAULT 'queued',
            progress INTEGER DEFAULT 0,
            file_name TEXT DEFAULT '',
            params TEXT DEFAULT '{}',
            error TEXT DEFAULT '',
            result_id TEXT DEFAULT '',
            duration_ms INTEGER DEFAULT 0,
            submitted_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON backtest_jobs(status);

        CREATE TABLE IF NOT EXISTS portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            items TEXT NOT NULL DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id TEXT PRIMARY KEY,
            strategy_id TEXT NOT NULL,
            rule TEXT NOT NULL,
            threshold TEXT NOT NULL,
            current_val TEXT NOT NULL,
            triggered INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1
        );
    """)
    db.commit()
    db.close()


def seed_data():
    """从 Parquet 数据生成种子数据（首次运行）"""
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM strategies").fetchone()[0]
    if count > 0:
        db.close()
        return  # 已有数据

    print("[Seed] 灌入种子数据...")
    from seed import run_seed
    run_seed(db)
    db.close()
    print("[Seed] 完成")
