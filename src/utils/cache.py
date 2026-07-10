#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - 翻译缓存管理器

本模块实现了翻译结果的本地持久化缓存，避免重复调用 LLM API。

缓存设计：
- 键：图片绝对路径 + 文件修改时间戳的 MD5 哈希
- 值：原文、译文、总结数据、写入时间戳
- 存储：config.json 同级目录下的 translation_cache.db（SQLite）
- 容量：上限 2000 条，LRU 淘汰策略
- 生命周期：程序启动时初始化 SQLite 连接，检测旧 JSON → 自动迁移
"""

import os
import sys
import hashlib
import logging
import threading

from utils.config import MAX_CACHE_ENTRIES

_logger = logging.getLogger("BubbleTrans")

# 缓存文件名（用于旧 JSON 检测）
CACHE_FILENAME = "translation_cache.json"


class TranslationCache:
    """
    翻译缓存管理器

    基于 SQLite 实现持久化缓存：
    - 读/写/清除操作委托给 Database 实例
    - save() 变为 no-op（SQLite 即時落盘）
    - _make_key() 和 _is_error_entry() 保留不变
    """

    def __init__(self, cache_path=None):
        """
        初始化缓存管理器

        参数:
            cache_path: 缓存文件路径（可选，用于检测旧 JSON）
        """
        if cache_path is None:
            # 缓存目录：优先使用 exe/py 所在目录（与 config.json 同级）
            # PyInstaller 打包后 __file__ 指向临时目录，需用 sys.executable 修正
            if getattr(sys, 'frozen', False):
                _project_root = os.path.dirname(os.path.abspath(sys.executable))
            else:
                # src/utils/cache.py → src/utils → src → 项目根目录
                _dir = os.path.dirname(os.path.abspath(__file__))
                _project_root = os.path.dirname(os.path.dirname(_dir))
            cache_path = os.path.join(_project_root, CACHE_FILENAME)

        self.cache_path = cache_path
        self._lock = threading.RLock()

        from utils.database import Database
        db_path = cache_path.replace('.json', '.db')
        self._db = Database(db_path, max_entries=MAX_CACHE_ENTRIES)

        # 检测并执行 JSON → SQLite 迁移
        json_path = cache_path
        if os.path.exists(json_path):
            _logger.info("检测到旧 JSON 缓存，开始迁移到 SQLite...")
            self._db.migrate_from_json(json_path)

    # ===================== 缓存操作 =====================

    def _make_key(self, image_path, mtime):
        """
        生成缓存键

        参数:
            image_path: 图片文件的绝对路径
            mtime: 文件修改时间戳（浮点数）

        返回:
            MD5 十六进制字符串

        注意：mtime 取整，兼容压缩包解压场景（ZIP 时间戳精度 2 秒，
        重新解压时子秒级漂移导致 key 不匹配）。
        """
        raw = f"{image_path}:{int(mtime)}"
        return hashlib.md5(raw.encode('utf-8')).hexdigest()

    def get(self, image_path, mtime):
        """
        查询缓存

        参数:
            image_path: 图片文件路径
            mtime: 文件修改时间戳

        返回:
            命中时返回 dict，未命中返回 None
        """
        with self._lock:
            key = self._make_key(image_path, mtime)
            entry = self._db.get(key)
            if entry is not None:
                # 过滤错误缓存：原文为空且译文包含错误关键词
                if self._is_error_entry(entry):
                    _logger.info(f"检测到错误缓存，跳过: {os.path.basename(image_path)}")
                    self._db.clear_image(image_path)
                    return None
                _logger.info(f"缓存命中: {os.path.basename(image_path)} (key={key[:8]}...)")
                # 兼容旧接口：返回的 dict 需包含 summary 字段
                return {
                    "image_path": entry.get("image_path", ""),
                    "original": entry.get("original", ""),
                    "translated": entry.get("translated", ""),
                    "summary": {
                        "plot": entry.get("plot", ""),
                        "notes": entry.get("notes", ""),
                    },
                    "timestamp": entry.get("updated_at", ""),
                }
            _logger.info(f"缓存未命中: {os.path.basename(image_path)} (key={key[:8]}...) total={self._db.count()})")
            return None

    def set(self, image_path, mtime, data, page_index=None):
        """
        写入缓存

        参数:
            image_path: 图片文件路径
            mtime: 文件修改时间戳
            data: {"original": str, "translated": str, "summary": dict}
            page_index: 页码（0-based，翻译启动时捕获）
        """
        with self._lock:
            key = self._make_key(image_path, mtime)
            folder_path = os.path.dirname(image_path)
            summary = data.get("summary", {}) or {}
            self._db.set(
                cache_key=key,
                folder_path=folder_path,
                page_index=page_index,  # None 时 SQLite 存 NULL
                image_path=image_path,
                original=data.get("original", ""),
                translated=data.get("translated", ""),
                plot=summary.get("plot", "") if isinstance(summary, dict) else "",
                notes=summary.get("notes", "") if isinstance(summary, dict) else "",
            )
            _logger.info(f"缓存写入: {os.path.basename(image_path)} (key={key[:8]}...) total={self._db.count()}")

    def save(self):
        """
        持久化缓存（no-op）
        SQLite 每次 set 即时落盘，无需显式保存。
        保留此空方法以兼容旧调用方。
        """
        pass

    # ===================== 降级查询 =====================

    def get_fallback(self, image_path):
        """
        API 失败时的降级兜底：查找同一图片的任意历史缓存（忽略 mtime）

        参数:
            image_path: 图片文件路径

        返回:
            命中时返回 dict，未命中返回 None
        """
        with self._lock:
            entry = self._db.get_fallback(image_path)
            if entry is not None:
                # 过滤错误缓存
                if self._is_error_entry(entry):
                    _logger.info(f"降级查询跳过错误缓存: {os.path.basename(image_path)}")
                    return None
                _logger.info(f"缓存降级命中: {os.path.basename(image_path)}")
                return {
                    "image_path": entry.get("image_path", ""),
                    "original": entry.get("original", ""),
                    "translated": entry.get("translated", ""),
                    "summary": {
                        "plot": entry.get("plot", ""),
                        "notes": entry.get("notes", ""),
                    },
                    "timestamp": entry.get("updated_at", ""),
                }
            return None

    # ===================== 缓存管理 =====================

    def _is_error_entry(self, entry):
        """
        判断缓存条目是否为错误内容（如 API 限流 429 错误文本）

        错误缓存特征：原文为空，译文以 "Error:" / "API Error:" 开头或包含错误码
        """
        original = entry.get("original", "")
        translated = entry.get("translated", "")
        if not original and translated:
            if translated.startswith("Error:") or translated.startswith("API Error:"):
                return True
            if "Error code:" in translated:
                return True
        return False

    def clear_image(self, image_path):
        """
        清除指定图片的所有缓存条目（忽略 mtime）

        参数:
            image_path: 图片文件路径
        返回:
            清除的条目数
        """
        with self._lock:
            removed = self._db.clear_image(image_path)
            if removed:
                _logger.info(f"已清除 {image_path} 的 {removed} 条缓存")
            return removed

    def clear(self):
        """
        清除全部缓存

        返回:
            清除的条目数
        """
        with self._lock:
            count = self._db.clear_all()
            _logger.info(f"已清除全部缓存 ({count} 条)")
            return count

    def __len__(self):
        """返回当前缓存条目数"""
        with self._lock:
            return self._db.count()

    def close(self):
        """关闭缓存数据库连接（checkpoint + close）"""
        self._db.close()
