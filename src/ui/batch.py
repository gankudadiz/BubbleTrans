#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - 批量翻译管理器

实现多页批量翻译：分块调度、Worker 池、进度追踪、暂停/取消。
支持按页码范围分块并发翻译，结果自动写入缓存。
"""

import os
import time
import threading
import logging

from PyQt6.QtCore import QObject, pyqtSignal, QThread
from PyQt6.QtWidgets import QApplication

_logger = logging.getLogger("BubbleTrans")

CHUNK_SIZE = 5   # 每块页数
MAX_RANGE = 50   # 单次最大翻译页数


class BatchTranslationManager(QObject):
    """批量翻译管理器：分块调度 + Worker 池 + 进度追踪

    在 start() 调用线程同步执行分块循环，但通过高频 processEvents()
    保持 UI 响应。TranslationWorker 本身在独立 QThread 中运行，
    因此翻译过程不阻塞主线程。
    """

    # 信号
    progress_updated = pyqtSignal(int, int)    # (completed, total)
    batch_finished = pyqtSignal(int, int)       # (success, failed)
    batch_paused = pyqtSignal()
    batch_resumed = pyqtSignal()

    def __init__(self, translation_cache, max_concurrent=2, parent=None):
        super().__init__(parent)
        self._cache = translation_cache
        self._max_concurrent = max_concurrent
        self._workers = []
        self._paused = False
        self._cancelled = False
        self._completed = 0
        self._failed = 0
        self._total = 0
        self._context_engine = None

    def set_context_engine(self, engine):
        """设置上下文引擎（PDR-03 提供）"""
        self._context_engine = engine

    # ===================== 核心操作 =====================

    def start(self, file_paths, start_page, end_page):
        """启动批量翻译（同步执行，高频 pump 事件保持 UI 响应）"""
        if not file_paths:
            return

        self._completed = 0
        self._failed = 0
        self._total = len(file_paths)
        self._cancelled = False
        self._paused = False

        # 分块
        chunks = []
        for i in range(0, self._total, CHUNK_SIZE):
            chunk_paths = file_paths[i:i + CHUNK_SIZE]
            chunk_start_page = start_page + i
            chunks.append((chunk_paths, chunk_start_page))

        for chunk_paths, chunk_start_page in chunks:
            # 暂停检查
            while self._paused and not self._cancelled:
                QApplication.processEvents()
                QThread.msleep(50)

            if self._cancelled:
                break

            # 构建上下文
            context = None
            if self._context_engine:
                try:
                    folder = os.path.dirname(chunk_paths[0])
                    context = self._context_engine.build_context(
                        folder, chunk_start_page, window_size=5
                    )
                except Exception:
                    pass

            # 处理当前块
            results = self._process_chunk(chunk_paths, chunk_start_page)

            # 写入缓存 + 更新进度
            for path, result in results.items():
                if result is not None:
                    origin, translated, summary = result
                    page_index = chunk_start_page + chunk_paths.index(path)
                    self._write_cache(path, page_index, origin, translated, summary)
                    self._completed += 1
                else:
                    self._failed += 1

            self.progress_updated.emit(self._completed, self._total)
            QApplication.processEvents()  # 让 UI 立即刷新进度条

            if self._cancelled:
                break

        self.progress_updated.emit(self._completed, self._total)
        self.batch_finished.emit(self._completed, self._failed)

    def pause(self):
        self._paused = True
        self.batch_paused.emit()

    def resume(self):
        self._paused = False
        self.batch_resumed.emit()

    def cancel(self):
        self._cancelled = True
        for w in self._workers:
            if w.isRunning():
                w.terminate()
                w.wait(500)
        self._workers.clear()

    def is_running(self):
        """start() 是同步的，返回 True 仅当未取消且未完成"""
        return not self._cancelled and self._completed < self._total

    def is_paused(self):
        return self._paused

    def progress(self):
        return (self._completed, self._total)

    # ===================== 内部方法 =====================

    def _write_cache(self, image_path, page_index, origin, translated, summary):
        """写入缓存（静默，不输出 INFO 日志避免批量 I/O 卡顿）"""
        try:
            mtime = os.path.getmtime(image_path)
            self._cache.set(image_path, mtime, {
                "original": origin,
                "translated": translated,
                "summary": summary,
            }, page_index=page_index)
        except Exception:
            pass

    def _process_chunk(self, chunk_paths, chunk_start_page):
        """组内并发翻译：启动所有 worker，高频 poll 等待完成"""
        from engine.workers import TranslationWorker

        workers = []
        results = {}
        lock = threading.Lock()
        completed_count = [0]
        total = len(chunk_paths)
        event = threading.Event()

        def on_page_done(path, origin, translated, summary):
            with lock:
                results[path] = (origin, translated, summary)
                completed_count[0] += 1
                if completed_count[0] == total:
                    event.set()

        def on_page_error(path, error_msg):
            with lock:
                results[path] = None
                completed_count[0] += 1
                if completed_count[0] == total:
                    event.set()

        for path in chunk_paths:
            worker = TranslationWorker(path)
            worker.finished.connect(
                lambda o, t, s, p=path: on_page_done(p, o, t, s)
            )
            worker.error.connect(
                lambda e, p=path: on_page_error(p, e)
            )
            workers.append(worker)

        self._workers = workers

        for w in workers:
            w.start()

        # 高频 poll（每 20ms），保证 UI 流畅
        deadline = time.time() + 300
        while time.time() < deadline:
            if event.wait(timeout=0.02):
                break
            QApplication.processEvents()
            if self._cancelled:
                for w in workers:
                    if w.isRunning():
                        w.terminate()
                        w.wait(500)
                break

        # 清理
        for w in workers:
            w.deleteLater()
        self._workers = []

        return results
