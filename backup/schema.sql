-- health.db schema — 个人健康数据库（SQLite，零依赖）
-- DB 文件在本地，脚本只查 DB，不碰 iCloud 文件（根治 iCloud evict 问题）
-- 6 张表：metrics / sleep_sessions / looki_moments / calendar_events / daily_briefs / daily_context

CREATE TABLE IF NOT EXISTS metrics (
    date TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value REAL,
    unit TEXT,
    source TEXT DEFAULT 'HAE',
    imported_at TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (date, metric_name, source)
);

CREATE TABLE IF NOT EXISTS sleep_sessions (
    sleep_date TEXT PRIMARY KEY,
    start_time TEXT,
    end_time TEXT,
    total_hours REAL,
    deep_hours REAL,
    rem_hours REAL,
    source TEXT DEFAULT 'HAE',
    imported_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS looki_moments (
    start_time TEXT,
    end_time TEXT,
    title TEXT,
    description TEXT,
    on_date TEXT,
    imported_at TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (start_time, end_time)
);

CREATE TABLE IF NOT EXISTS calendar_events (
    start_time TEXT,
    end_time TEXT,
    summary TEXT,
    rsvp TEXT,
    organizer TEXT,
    on_date TEXT,
    PRIMARY KEY (start_time, summary)
);

CREATE TABLE IF NOT EXISTS daily_briefs (
    date TEXT PRIMARY KEY,
    content TEXT,
    verdict TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS daily_context (
    date TEXT PRIMARY KEY,
    alcohol INTEGER,
    late_meal INTEGER,
    caffeine_cutoff TEXT,
    social_stress INTEGER,
    exercise TEXT,
    sleep_subjective INTEGER,
    note TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_metrics_date ON metrics(date);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(metric_name);
