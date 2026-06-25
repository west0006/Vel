-- 智能AI桌宠 Vel 数据库 schema
-- SQLite 3, WAL 模式
-- 敏感字段在应用层使用 AES-256-GCM 加密

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA encoding = 'UTF-8';

-- =============================================
-- 用户画像模块
-- =============================================

-- 用户固定属性（键值对）
CREATE TABLE IF NOT EXISTS user_profile (
                                            key         TEXT PRIMARY KEY,
                                            value       TEXT NOT NULL,              -- 敏感字段 AES 加密
                                            confidence  REAL DEFAULT 1.0,
                                            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                                            updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 习得特质
CREATE TABLE IF NOT EXISTS user_traits (
                                           trait_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                                           trait_name  TEXT NOT NULL,              -- 如 prefer_light_food
                                           value       TEXT NOT NULL,              -- 如 spicy_level: low
                                           evidence    TEXT,                       -- 对话证据摘要
                                           occurrences INTEGER DEFAULT 1,
                                           confidence  REAL DEFAULT 0.6,
                                           first_seen  DATETIME DEFAULT CURRENT_TIMESTAMP,
                                           last_active DATETIME DEFAULT CURRENT_TIMESTAMP,
                                           source      TEXT DEFAULT 'auto'         -- auto / manual
);
CREATE INDEX IF NOT EXISTS idx_traits_active ON user_traits(last_active, confidence);

-- =============================================
-- 记忆系统模块
-- =============================================

-- 情节记忆
CREATE TABLE IF NOT EXISTS episodic_memory (
                                               memory_id      TEXT PRIMARY KEY,        -- UUID
                                               summary        TEXT NOT NULL,           -- AES 加密
                                               category       TEXT NOT NULL,           -- event / preference / habit / fact
                                               importance     INTEGER DEFAULT 5,       -- 1~10
                                               created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
                                               last_recalled  DATETIME,
                                               decay_factor   REAL DEFAULT 1.0,
                                               embedding_id   TEXT,                    -- FAISS 索引 ID
                                               context_msg_ids TEXT                    -- JSON 数组
);
CREATE INDEX IF NOT EXISTS idx_memory_category ON episodic_memory(category);
CREATE INDEX IF NOT EXISTS idx_memory_importance ON episodic_memory(importance);

-- 对话原始记录
CREATE TABLE IF NOT EXISTS conversation_archive (
                                                    msg_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                                                    timestamp    DATETIME DEFAULT CURRENT_TIMESTAMP,
                                                    role         TEXT NOT NULL,             -- user / assistant
                                                    content      TEXT NOT NULL,
                                                    emotion_label TEXT,                     -- 情感标签
                                                    tokens_count INTEGER
);
CREATE INDEX IF NOT EXISTS idx_conv_time ON conversation_archive(timestamp);

-- =============================================
-- 健康管理模块
-- =============================================

-- 饮食记录
CREATE TABLE IF NOT EXISTS meal_log (
                                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                                        timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP,
                                        meal_type   TEXT NOT NULL,              -- breakfast / lunch / dinner / snack
                                        content     TEXT NOT NULL,
                                        source      TEXT DEFAULT 'manual',      -- recommendation / manual
                                        location_id TEXT,                       -- 高德 POI ID
                                        accepted    BOOLEAN DEFAULT 1,
                                        notes       TEXT
);
CREATE INDEX IF NOT EXISTS idx_meal_time_type ON meal_log(timestamp, meal_type);

-- 饮水记录
CREATE TABLE IF NOT EXISTS drink_log (
                                         id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                                         timestamp             DATETIME DEFAULT CURRENT_TIMESTAMP,
                                         amount_ml             INTEGER DEFAULT 250,
                                         triggered_by_reminder BOOLEAN DEFAULT 0
);

-- 活动记录
CREATE TABLE IF NOT EXISTS activity_log (
                                            id            INTEGER PRIMARY KEY AUTOINCREMENT,
                                            start_time    DATETIME NOT NULL,
                                            end_time      DATETIME,
                                            activity_type TEXT NOT NULL,            -- stretch / eye_exercise / walk / other
                                            duration_min  INTEGER,
                                            source        TEXT DEFAULT 'reminder'   -- reminder / manual
);

-- 作息记录
CREATE TABLE IF NOT EXISTS sleep_log (
                                         date                DATE PRIMARY KEY,
                                         sleep_time_estimate DATETIME,
                                         wake_time_estimate  DATETIME,
                                         confidence          REAL DEFAULT 0.5,
                                         manual_override     BOOLEAN DEFAULT 0
);

-- 情绪快照
CREATE TABLE IF NOT EXISTS mood_snapshot (
                                             id              INTEGER PRIMARY KEY AUTOINCREMENT,
                                             timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
                                             mood_label      TEXT NOT NULL,          -- positive / neutral / negative
                                             intensity       REAL DEFAULT 0.5,       -- 0~1
                                             context_msg_id  INTEGER,               -- 关联 conversation_archive.msg_id
                                             context_summary TEXT
);
CREATE INDEX IF NOT EXISTS idx_mood_time_label ON mood_snapshot(timestamp, mood_label);

-- =============================================
-- 日程提醒模块
-- =============================================

-- 日程主表
CREATE TABLE IF NOT EXISTS schedule (
                                        id                 TEXT PRIMARY KEY,    -- UUID
                                        title              TEXT NOT NULL,
                                        description        TEXT,
                                        start_time         DATETIME NOT NULL,
                                        end_time           DATETIME,
                                        is_all_day         INTEGER DEFAULT 0,
                                        recurrence_rule    TEXT,                -- RFC 5545
                                        reminder_offset_min INTEGER DEFAULT 15,
                                        priority           INTEGER DEFAULT 1,  -- 0低 / 1中 / 2高
                                        status             TEXT DEFAULT 'active', -- active / completed / cancelled / missed
                                        created_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
                                        updated_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
                                        source             TEXT DEFAULT 'manual', -- manual / ocr / import
                                        location           TEXT
);
CREATE INDEX IF NOT EXISTS idx_schedule_start ON schedule(start_time);
CREATE INDEX IF NOT EXISTS idx_schedule_status ON schedule(status);

-- 重复日程实例
CREATE TABLE IF NOT EXISTS schedule_instance (
                                                 instance_id   TEXT PRIMARY KEY,         -- UUID
                                                 schedule_id   TEXT NOT NULL REFERENCES schedule(id),
    original_start DATETIME NOT NULL,
    actual_start  DATETIME,
    status        TEXT DEFAULT 'active',
    note          TEXT
    );
CREATE INDEX IF NOT EXISTS idx_instance_schedule ON schedule_instance(schedule_id);
CREATE INDEX IF NOT EXISTS idx_instance_start ON schedule_instance(actual_start);

-- =============================================
-- 系统与缓存模块
-- =============================================

-- 搜索缓存
CREATE TABLE IF NOT EXISTS search_cache (
                                            id           INTEGER PRIMARY KEY AUTOINCREMENT,
                                            query_hash   TEXT UNIQUE NOT NULL,      -- SHA256
                                            result_json  TEXT,
                                            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                                            ttl_seconds  INTEGER DEFAULT 1800
);

-- 位置缓存
CREATE TABLE IF NOT EXISTS location_cache (
                                              id              INTEGER PRIMARY KEY AUTOINCREMENT,
                                              coord_key       TEXT NOT NULL,
                                              query_keywords  TEXT NOT NULL,
                                              result_json     TEXT,
                                              created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_location_cache ON location_cache(coord_key, query_keywords);

-- 应用设置（键值对）
CREATE TABLE IF NOT EXISTS app_settings (
                                            key        TEXT PRIMARY KEY,
                                            value      TEXT NOT NULL,
                                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 更新信息（仅1行）
CREATE TABLE IF NOT EXISTS update_info (
                                           id               INTEGER PRIMARY KEY CHECK(id = 1),
    current_version  TEXT NOT NULL,
    last_check_time  DATETIME,
    latest_version   TEXT,
    download_url     TEXT,
    sha256           TEXT,
    update_status    TEXT DEFAULT 'none'    -- none / downloading / ready / failed
    );

-- =============================================
-- 默认数据插入
-- =============================================

-- 默认应用设置
INSERT OR IGNORE INTO app_settings (key, value) VALUES
    ('drink_interval_min', '45'),
    ('drink_daily_target_ml', '2000'),
    ('sedentary_threshold_min', '50'),
    ('active_hours_start', '09:00'),
    ('active_hours_end', '21:00'),
    ('sleep_start', '23:00'),
    ('sleep_end', '07:00'),
    ('notification_quiet_start', ''),
    ('notification_quiet_end', ''),
    ('voice_enabled', 'false'),
    ('search_safe_mode', 'true'),
    ('gaode_daily_count', '0'),
    ('gaode_daily_date', ''),
    ('bing_monthly_count', '0'),
    ('bing_monthly_month', '');

-- 默认更新信息
INSERT OR IGNORE INTO update_info (id, current_version)
    VALUES (1, '0.1.0-alpha');



CREATE TABLE IF NOT EXISTS memo (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    remind_at DATETIME,
    status TEXT DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_diary (
    date DATE PRIMARY KEY,
    summary TEXT NOT NULL,
    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS habit (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    target_time TEXT NOT NULL DEFAULT '21:00',
    streak INTEGER DEFAULT 0,
    longest_streak INTEGER DEFAULT 0,
    total_completions INTEGER DEFAULT 0,
    last_check_date TEXT,
    enabled INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);