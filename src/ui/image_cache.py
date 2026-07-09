#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - 图片缓存管理器

QPixmap LRU 缓存 + 后台异步解码 + 相邻页预加载。
"""

from collections import OrderedDict
from PyQt6.QtCore import QObject, pyqtSignal
from engine.workers import ImageLoadWorker


class ImageCacheManager(QObject):
    """管理图片解码缓存和异步加载生命周期"""

    # 信号：主动加载完成（需要 window 决定是否渲染）
    image_loaded = pyqtSignal(str, object)         # path, QPixmap
    image_error = pyqtSignal(str, str)              # path, error_msg

    # 信号：预加载完成（静默入缓存，不需要渲染）
    prefetch_completed = pyqtSignal(str, object)    # path, QPixmap

    def __init__(self, max_cache_size=10, prefetch_range=2, parent=None):
        super().__init__(parent)
        self._cache = OrderedDict()          # path → QPixmap
        self._pending = {}                   # path → ImageLoadWorker
        self.max_cache_size = max_cache_size
        self.prefetch_range = prefetch_range

    # --- 缓存查询 ---
    def get(self, path):
        """查缓存，命中返回 QPixmap 并更新 LRU 位置；未命中返回 None"""
        if path in self._cache:
            self._cache.move_to_end(path)
            return self._cache[path]
        return None

    def has(self, path):
        return path in self._cache

    # --- 异步加载 ---
    def load_async(self, path):
        """主动加载：创建 worker 解码，完成时发射 image_loaded"""
        if path in self._pending:
            return
        worker = ImageLoadWorker(path)
        worker.loaded.connect(self._on_load_done)
        worker.error.connect(self._on_load_error)
        self._pending[path] = worker
        worker.start()

    def _on_load_done(self, image_path, pixmap):
        self._add_to_cache(image_path, pixmap)
        self._pending.pop(image_path, None)
        self.image_loaded.emit(image_path, pixmap)

    def _on_load_error(self, image_path, error_msg):
        self._pending.pop(image_path, None)
        self.image_error.emit(image_path, error_msg)

    # --- 预加载 ---
    def prefetch(self, paths):
        """后台预加载：跳过已缓存/进行中的，静默加入后台"""
        for path in paths:
            if path in self._cache or path in self._pending:
                continue
            worker = ImageLoadWorker(path)
            worker.loaded.connect(self._on_prefetch_done)
            worker.error.connect(lambda p, e, w=worker: self._pending.pop(p, None))
            self._pending[path] = worker
            worker.start()

    def _on_prefetch_done(self, image_path, pixmap):
        self._add_to_cache(image_path, pixmap)
        self._pending.pop(image_path, None)
        self.prefetch_completed.emit(image_path, pixmap)

    # --- 缓存写入 ---
    def _add_to_cache(self, path, pixmap):
        if path in self._cache:
            self._cache.move_to_end(path)
        self._cache[path] = pixmap
        if len(self._cache) > self.max_cache_size:
            self._cache.popitem(last=False)

    # --- 清理 ---
    def cancel_pending(self, path):
        worker = self._pending.pop(path, None)
        if worker and worker.isRunning():
            worker.terminate()
            worker.wait(500)
            worker.deleteLater()

    def clear(self):
        """清空全部缓存 + 终止全部进行中的 worker"""
        self._cache.clear()
        for path, worker in list(self._pending.items()):
            if worker.isRunning():
                worker.terminate()
                worker.wait(500)
                worker.deleteLater()
        self._pending.clear()
