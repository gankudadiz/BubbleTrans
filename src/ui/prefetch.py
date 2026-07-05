#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - 预翻译管理器

实现后台预翻译功能：用户翻页时，后台提前翻译后续 N 页并写入缓存，
翻到该页时直接从缓存读取，实现秒出结果。
"""

import os
import logging
import collections

from PyQt6.QtCore import QObject, pyqtSignal

_logger = logging.getLogger("BubbleTrans")


class PrefetchManager(QObject):
    """预翻译管理器 - 在后台提前翻译后续页面并缓存"""

    # 信号
    progress_changed = pyqtSignal(int, int)    # (completed, total)
    page_completed = pyqtSignal(str)           # image_path
    all_completed = pyqtSignal()               # 全部完成

    def __init__(self, cache, max_concurrent=2):
        """
        初始化预翻译管理器

        参数:
            cache: TranslationCache 实例
            max_concurrent: 最大并发 worker 数（默认 2）
        """
        super().__init__()
        self._cache = cache
        self._max_concurrent = max_concurrent
        self._queue = collections.deque()      # 待翻译路径队列
        self._queue_set = set()                # 队列路径集合（O(1) 查重用）
        self._active = {}                      # path -> TranslationWorker
        self._total = 0                        # 总任务数（queue + active）
        self._completed = 0                    # 已完成数

    # ===================== 公开接口 =====================

    def enqueue(self, paths):
        """
        将路径列表加入预翻译队列

        自动跳过：
        - 缓存已命中的路径
        - 已在队列中的路径
        - 正在翻译中的路径

        参数:
            paths: 图片路径列表
        """
        added = 0
        for path in paths:
            # 跳过已在队列中的
            if path in self._queue_set:
                continue
            # 跳过正在翻译中的
            if path in self._active:
                continue
            # 跳过缓存已命中的
            try:
                mtime = os.path.getmtime(path)
                if self._cache.get(path, mtime) is not None:
                    continue
            except OSError:
                _logger.warning(f"预翻译跳过（无法访问文件）: {path}")
                continue

            self._queue.append(path)
            self._queue_set.add(path)
            added += 1

        if added > 0:
            self._total = len(self._queue) + len(self._active)
            self._process_queue()

    def promote(self, path):
        """
        将指定路径从队列中移除（用户按 F5 翻译当前页时调用）

        如果该路径正在 active 中（正在翻译），不终止，让它自然完成。

        参数:
            path: 要移除的图片路径
        """
        if path not in self._queue_set:
            return

        self._queue_set.discard(path)
        # 从 deque 中过滤掉指定 path
        self._queue = collections.deque(
            p for p in self._queue if p != path
        )
        self._total = len(self._queue) + len(self._active)

    def resync(self, current_idx, page_paths, prefetch_count):
        """
        根据当前页码重新同步预翻译队列

        计算目标预翻译范围，移除不在范围内的队列项，
        添加未缓存/未在队列/未在 active 中的目标路径。

        参数:
            current_idx: 当前页码索引（从 0 开始）
            page_paths:  所有页面路径的有序列表
            prefetch_count: 预翻译页数（从当前页之后开始计算）
        """
        total_pages = len(page_paths)
        if current_idx >= total_pages - 1:
            # 已是最后一页，无需预翻译，清空队列
            self._queue.clear()
            self._queue_set.clear()
            self._total = len(self._active)
            return

        # 计算目标范围
        target_start = current_idx + 1
        target_end = min(current_idx + prefetch_count, total_pages - 1)
        target_paths = set(page_paths[target_start:target_end + 1])

        # 移除队列中不在目标范围内的项
        to_remove = [p for p in self._queue if p not in target_paths]
        for p in to_remove:
            self._queue_set.discard(p)
        if to_remove:
            self._queue = collections.deque(
                p for p in self._queue if p in target_paths
            )

        # 添加目标范围内未在 queue/active/缓存中的项
        added = 0
        for path in target_paths:
            if path in self._queue_set or path in self._active:
                continue
            try:
                mtime = os.path.getmtime(path)
                if self._cache.get(path, mtime) is not None:
                    continue
            except OSError:
                _logger.warning(f"预翻译跳过（无法访问文件）: {path}")
                continue
            self._queue.append(path)
            self._queue_set.add(path)
            added += 1

        if added > 0 or to_remove:
            self._total = len(self._queue) + len(self._active)

        self._process_queue()

    def clear(self):
        """
        清空所有预翻译任务（静默清理，不发射信号）

        终止所有进行中的 worker 并释放 Qt 资源。
        """
        self._queue.clear()
        self._queue_set.clear()

        for path, worker in list(self._active.items()):
            if worker.isRunning():
                worker.terminate()
                worker.wait(500)
                worker.deleteLater()
        self._active.clear()

        self._total = 0
        self._completed = 0

    # ===================== 内部方法 =====================

    def _process_queue(self):
        """
        处理队列：启动新的 worker 直到达到最大并发数

        延迟导入 TranslationWorker 以避免循环依赖（window.py 可能导入本模块）。
        """
        # 延迟导入避免循环依赖
        from ui.window import TranslationWorker

        while len(self._active) < self._max_concurrent and self._queue:
            path = self._queue.popleft()
            self._queue_set.discard(path)

            worker = TranslationWorker(path)
            # 用 lambda 默认参数捕获 path，区分不同 worker 的信号
            worker.finished.connect(
                lambda o, t, s, p=path: self._on_worker_finished(p, o, t, s)
            )
            worker.error.connect(
                lambda e, p=path: self._on_worker_error(p, e)
            )

            self._active[path] = worker
            worker.start()

    def _on_worker_finished(self, path, origin_text, translated_text, summary_dict):
        """worker 翻译完成回调 - 写入缓存并更新状态"""
        # 写入缓存
        try:
            mtime = os.path.getmtime(path)
            self._cache.set(path, mtime, {
                "original": origin_text,
                "translated": translated_text,
                "summary": summary_dict,
            })
            self._cache.save()
        except Exception as e:
            _logger.warning(f"预翻译缓存写入失败 ({path}): {e}")

        # 发射单页完成信号（让 window 判断是否需要刷新 UI）
        self.page_completed.emit(path)
        # 公共清理：移除 worker → 更新计数 → 调度下一个 → 检查全部完成
        self._on_worker_done(path)

    def _on_worker_error(self, path, error_msg):
        """worker 翻译出错回调 - 静默跳过"""
        _logger.warning(f"预翻译出错 ({path}): {error_msg}")
        self._on_worker_done(path)

    def _on_worker_done(self, path):
        """
        worker 结束后的公共清理逻辑

        从 active 中移除已完成（或失败）的 worker，
        更新进度计数，取下一个排队任务，检查是否全部完成。
        """
        self._active.pop(path, None)
        self._completed += 1
        self.progress_changed.emit(self._completed, self._total)
        self._process_queue()

        # 全部完成：发射信号并重置计数
        if not self._queue and not self._active:
            self.all_completed.emit()
            self._total = 0
            self._completed = 0
