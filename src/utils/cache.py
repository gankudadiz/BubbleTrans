#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - 翻译缓存管理器

本模块实现了翻译结果的本地持久化缓存，避免重复调用 LLM API。

缓存设计：
- 键：图片绝对路径 + 文件修改时间戳的 MD5 哈希
- 值：原文、译文、总结数据、写入时间戳
- 存储：config.json 同级目录下的 translation_cache.json
- 容量：上限 500 条，LRU 淘汰策略
- 生命周期：程序启动时一次性加载到内存，翻译成功后增量写入磁盘
"""

import os
import sys
import json
import hashlib
import logging
from collections import OrderedDict

_logger = logging.getLogger("BubbleTrans")

# 最大缓存条目数
MAX_ENTRIES = 500

# 缓存文件名
CACHE_FILENAME = "translation_cache.json"


class TranslationCache:
    """
    翻译缓存管理器

    基于 OrderedDict 实现 LRU 淘汰：
    - 每次 get() 命中时将条目移到末尾（标记最近使用）
    - set() 新条目插入末尾
    - 超出上限时 popitem(last=False) 淘汰最久未用的条目
    """

    def __init__(self, cache_path=None):
        """
        初始化缓存管理器

        参数:
            cache_path: 缓存文件路径（可选）
                       默认取项目根目录下的 translation_cache.json
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
        self._data = OrderedDict()
        self._load()

    # ===================== 磁盘 I/O =====================

    def _load(self):
        """从 JSON 文件加载缓存到内存，自动过滤错误条目"""
        if not os.path.exists(self.cache_path):
            _logger.info("缓存文件不存在，将创建新缓存")
            return

        try:
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            # 按时间戳升序插入（最早的在前面，LRU 淘汰时优先移除）
            cleaned = 0
            sorted_items = []
            for key, entry in sorted(raw.items(), key=lambda kv: kv[1].get("timestamp", 0)):
                if self._is_error_entry(entry):
                    cleaned += 1
                    continue
                sorted_items.append((key, entry))
            self._data = OrderedDict(sorted_items)
            if cleaned:
                _logger.info(f"已加载 {len(self._data)} 条翻译缓存（自动过滤 {cleaned} 条错误缓存）")
                # 立即写回磁盘，清除错误条目
                self.save()
            else:
                _logger.info(f"已加载 {len(self._data)} 条翻译缓存")
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            _logger.warning(f"缓存文件损坏 ({e})，将创建新缓存")
            self._data = OrderedDict()
        except Exception as e:
            _logger.warning(f"加载缓存失败: {e}")
            self._data = OrderedDict()

    def save(self):
        """持久化内存缓存到 JSON 文件"""
        try:
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            _logger.debug(f"缓存已保存 ({len(self._data)} 条)")
        except Exception as e:
            _logger.warning(f"保存缓存失败: {e}")

    # ===================== 缓存操作 =====================

    def _make_key(self, image_path, mtime):
        """
        生成缓存键

        参数:
            image_path: 图片文件的绝对路径
            mtime: 文件修改时间戳（浮点数）

        返回:
            MD5 十六进制字符串
        """
        raw = f"{image_path}:{mtime}"
        return hashlib.md5(raw.encode('utf-8')).hexdigest()

    def get(self, image_path, mtime):
        """
        查询缓存

        参数:
            image_path: 图片文件路径
            mtime: 文件修改时间戳

        返回:
            命中时返回 {"original": str, "translated": str, "summary": dict}
            未命中（或缓存为错误内容）返回 None
        """
        key = self._make_key(image_path, mtime)
        if key in self._data:
            self._data.move_to_end(key)
            entry = self._data[key]
            # 过滤错误缓存：原文为空且译文包含错误关键词
            if self._is_error_entry(entry):
                _logger.info(f"检测到错误缓存，跳过: {os.path.basename(image_path)}")
                del self._data[key]
                return None
            _logger.debug(f"缓存命中: {os.path.basename(image_path)}")
            return entry
        return None

    def set(self, image_path, mtime, data):
        """
        写入缓存

        参数:
            image_path: 图片文件路径
            mtime: 文件修改时间戳
            data: {"original": str, "translated": str, "summary": dict}
        """
        import time

        key = self._make_key(image_path, mtime)
        entry = {
            "image_path": image_path,
            "original": data.get("original", ""),
            "translated": data.get("translated", ""),
            "summary": data.get("summary", {}),
            "timestamp": time.time(),
        }

        # 如果已存在同一键（重复翻译同一文件同版本），移到末尾
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = entry

        # LRU 淘汰：超出上限时移除最旧的条目
        while len(self._data) > MAX_ENTRIES:
            self._data.popitem(last=False)

        _logger.debug(f"已缓存: {os.path.basename(image_path)} (共 {len(self._data)} 条)")

    # ===================== 降级查询 =====================

    def get_fallback(self, image_path):
        """
        API 失败时的降级兜底：查找同一图片的任意历史缓存（忽略 mtime）

        从最新到最旧遍历，返回第一个匹配的非错误缓存条目。
        用于 API 暂时不可用时仍能展示该图片的上一次翻译结果。

        参数:
            image_path: 图片文件路径

        返回:
            命中时返回 {"original": str, "translated": str, "summary": dict}
            无历史缓存（或仅有错误缓存）时返回 None
        """
        for key in reversed(self._data):
            entry = self._data[key]
            if entry.get("image_path") == image_path:
                if self._is_error_entry(entry):
                    continue  # 跳过错误缓存
                _logger.info(f"缓存降级命中: {os.path.basename(image_path)}")
                return entry
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
        removed = 0
        keys_to_remove = []
        for key, entry in self._data.items():
            if entry.get("image_path") == image_path:
                keys_to_remove.append(key)
        for key in keys_to_remove:
            del self._data[key]
            removed += 1
        if removed:
            _logger.info(f"已清除 {image_path} 的 {removed} 条缓存")
            self.save()
        return removed

    def clear(self):
        """
        清除全部缓存

        返回:
            清除的条目数
        """
        count = len(self._data)
        self._data.clear()
        self.save()
        _logger.info(f"已清除全部缓存 ({count} 条)")
        return count

    def __len__(self):
        """返回当前缓存条目数"""
        return len(self._data)
