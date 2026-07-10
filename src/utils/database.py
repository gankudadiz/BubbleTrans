#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - SQLite 存储层

纯 sqlite3（标准库），零额外依赖。
提供翻译缓存的持久化存储、CRUD、LRU 淘汰、JSON 迁移等功能。
"""

import os
import json
import time
import logging
import sqlite3
import threading

_logger = logging.getLogger("BubbleTrans")

# 默认数据库文件名
DB_FILENAME = "translation_cache.db"

# 写入重试次数
_WRITE_RETRIES = 3
_WRITE_RETRY_INTERVAL = 0.1  # 100ms


class Database:
    """SQLite 存储层"""

    def __init__(self, db_path=None, max_entries=2000):
        """
        初始化数据库连接

        参数:
            db_path: 数据库文件路径（默认与配置文件同目录）
            max_entries: LRU 上限
        """
        if db_path is None:
            if getattr(sys, 'frozen', False):
                _project_root = os.path.dirname(os.path.abspath(sys.executable))
            else:
                _dir = os.path.dirname(os.path.abspath(__file__))
                _project_root = os.path.dirname(os.path.dirname(_dir))
            db_path = os.path.join(_project_root, DB_FILENAME)

        self.db_path = db_path
        self.max_entries = max_entries
        self._lock = threading.RLock()

        # 创建连接
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._init_schema()

    def _init_schema(self):
        """创建表结构"""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS translations (
                cache_key   TEXT PRIMARY KEY,
                folder_path TEXT NOT NULL,
                page_index  INTEGER,
                image_path  TEXT NOT NULL,
                original    TEXT,
                translated  TEXT,
                plot        TEXT,
                notes       TEXT,
                updated_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_folder_page
                ON translations(folder_path, page_index);
            CREATE INDEX IF NOT EXISTS idx_image_path
                ON translations(image_path);
        """)
        self._conn.commit()

    # ===================== 写入（带重试） =====================

    def _execute_with_retry(self, sql, params=None):
        """写入操作带重试机制"""
        params = params or ()
        for attempt in range(_WRITE_RETRIES):
            try:
                cursor = self._conn.execute(sql, params)
                self._conn.commit()
                return cursor
            except sqlite3.OperationalError as e:
                _logger.warning(f"SQLite 写入重试 ({attempt + 1}/{_WRITE_RETRIES}): {e}")
                if attempt < _WRITE_RETRIES - 1:
                    time.sleep(_WRITE_RETRY_INTERVAL)
                else:
                    raise

    # ===================== JSON 迁移 =====================

    def migrate_from_json(self, json_path: str) -> int:
        """
        从 JSON 文件迁移数据到 SQLite

        逐条读取 JSON → INSERT OR REPLACE → 比对条数
        → 一致则重命名 .bak，不一致抛异常。

        参数:
            json_path: JSON 缓存文件路径

        返回:
            迁移的条目数

        抛出:
            ValueError: 条数不一致时
            json.JSONDecodeError: JSON 格式错误时
        """
        if not os.path.exists(json_path):
            _logger.info("JSON 缓存文件不存在，跳过迁移")
            return 0

        with open(json_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)

        if not isinstance(raw_data, dict):
            raise ValueError("JSON 缓存格式无效：应为字典结构")

        json_count = len(raw_data)
        if json_count == 0:
            _logger.info("JSON 缓存为空，跳过迁移")
            return 0

        # 逐条插入
        inserted = 0
        now = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
        for key, entry in raw_data.items():
            if not isinstance(entry, dict):
                continue
            image_path = entry.get("image_path", "")
            if not image_path:
                continue
            folder_path = os.path.dirname(image_path)
            original = entry.get("original", "")
            translated = entry.get("translated", "")
            summary = entry.get("summary", {}) or {}
            plot = summary.get("plot", "") if isinstance(summary, dict) else ""
            notes = summary.get("notes", "") if isinstance(summary, dict) else ""

            self._execute_with_retry("""
                INSERT OR REPLACE INTO translations
                (cache_key, folder_path, page_index, image_path, original, translated, plot, notes, updated_at)
                VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)
            """, (key, folder_path, image_path, original, translated, plot, notes, now))
            inserted += 1

        # 比对条数
        db_count = self.count()
        if db_count != json_count:
            raise ValueError(
                f"迁移条数不一致：JSON {json_count} 条，SQLite {db_count} 条。"
                f"保留 JSON 不动，请手动检查。"
            )

        # 一致 → 重命名 JSON 为 .bak
        bak_path = json_path + ".bak"
        try:
            os.rename(json_path, bak_path)
            _logger.info(f"JSON 迁移完成：{inserted} 条 → SQLite，原文件已重命名为 {os.path.basename(bak_path)}")
        except OSError as e:
            _logger.warning(f"重命名 JSON 失败: {e}")

        return inserted

    # ===================== CRUD =====================

    def get(self, cache_key: str) -> dict | None:
        """
        根据缓存键查询

        参数:
            cache_key: MD5(image_path + mtime)

        返回:
            命中时返回 dict，未命中返回 None
        """
        cursor = self._conn.execute(
            "SELECT * FROM translations WHERE cache_key = ?",
            (cache_key,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def set(self, cache_key: str, folder_path: str, page_index: int | None,
            image_path: str, original: str, translated: str,
            plot: str, notes: str) -> None:
        """
        写入缓存条目

        参数:
            cache_key: 缓存键
            folder_path: 所属文件夹路径
            page_index: 页码（0-based，可为 None）
            image_path: 图片绝对路径
            original: 原文
            translated: 译文
            plot: 剧情总结
            notes: 翻译备注
        """
        now = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
        self._execute_with_retry("""
            INSERT OR REPLACE INTO translations
            (cache_key, folder_path, page_index, image_path, original, translated, plot, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (cache_key, folder_path, page_index, image_path, original, translated, plot, notes, now))

        # 写入后检查 LRU
        self._evict_lru()

    def get_fallback(self, image_path: str) -> dict | None:
        """
        按 image_path 降级查询（忽略 mtime）

        返回最新的一个缓存条目（按 updated_at DESC）。

        参数:
            image_path: 图片绝对路径

        返回:
            命中时返回 dict，未命中返回 None
        """
        cursor = self._conn.execute("""
            SELECT * FROM translations
            WHERE image_path = ?
            ORDER BY updated_at DESC
            LIMIT 1
        """, (image_path,))
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def clear_image(self, image_path: str) -> int:
        """
        清除指定图片的所有缓存

        参数:
            image_path: 图片绝对路径

        返回:
            删除的条目数
        """
        cursor = self._execute_with_retry(
            "DELETE FROM translations WHERE image_path = ?",
            (image_path,)
        )
        return cursor.rowcount if cursor else 0

    def clear_all(self) -> int:
        """清除全部缓存，返回删除的条目数"""
        count = self.count()
        self._execute_with_retry("DELETE FROM translations")
        return count

    def count(self) -> int:
        """返回当前缓存条目数"""
        cursor = self._conn.execute("SELECT COUNT(*) AS cnt FROM translations")
        row = cursor.fetchone()
        return row["cnt"] if row else 0

    # ===================== 上下文查询 =====================

    def get_page_range(self, folder_path: str, start: int, end: int) -> list[dict]:
        """
        按文件夹 + 页码范围查询（为 PDR-03 准备）

        参数:
            folder_path: 文件夹绝对路径
            start: 起始页码（0-based，含）
            end: 结束页码（0-based，含）

        返回:
            page_index 在 [start, end] 范围内的条目列表
        """
        cursor = self._conn.execute("""
            SELECT * FROM translations
            WHERE folder_path = ?
              AND page_index >= ?
              AND page_index <= ?
            ORDER BY page_index ASC
        """, (folder_path, start, end))
        return [dict(row) for row in cursor.fetchall()]

    # ===================== LRU 淘汰 =====================

    def _evict_lru(self, max_entries=None):
        """
        LRU 淘汰：超出上限时按 updated_at ASC 删除最旧条目

        每次超额后一次性批量删除超出数量 + 10% 余量。

        参数:
            max_entries: 最大条目数（默认 self.max_entries）
        """
        if max_entries is None:
            max_entries = self.max_entries

        current = self.count()
        if current <= max_entries:
            return

        # 需删除数量 = 超出数量 + 10%
        excess = current - max_entries
        to_delete = excess + int(max_entries * 0.1)
        if to_delete <= 0:
            return

        _logger.debug(f"LRU 淘汰：当前 {current} 条，上限 {max_entries}，删除 {to_delete} 条")
        self._execute_with_retry("""
            DELETE FROM translations
            WHERE cache_key IN (
                SELECT cache_key FROM translations
                ORDER BY updated_at ASC
                LIMIT ?
            )
        """, (to_delete,))

    # ===================== 连接管理 =====================

    def close(self):
        """关闭数据库连接（先 checkpoint 确保数据不丢失）"""
        try:
            if self._conn:
                # WAL checkpoint：确保所有修改写入主数据库文件
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                self._conn.close()
                _logger.debug("数据库连接已关闭（已 checkpoint）")
        except Exception as e:
            _logger.warning(f"关闭数据库连接时出错: {e}")


# 为 module 级别引入 sys（避免 __init__ 中循环导入问题）
import sys
