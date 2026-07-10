#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - 翻译编排控制器

管理翻译任务的完整生命周期：Worker 创建/启动/终止、缓存写回、临时文件清理。
"""

import os
import uuid
import tempfile
from PyQt6.QtCore import QObject, pyqtSignal
from engine.llm import llm_engine
from engine.workers import TranslationWorker


class TranslationController(QObject):
    """翻译任务编排器"""

    stage_changed = pyqtSignal(str)
    translating_changed = pyqtSignal(bool)
    translation_finished = pyqtSignal(str, str, dict)  # origin, translated, summary
    translation_error = pyqtSignal(str)
    translation_started = pyqtSignal()

    def __init__(self, translation_cache, parent=None):
        super().__init__(parent)
        self._cache = translation_cache
        self._worker = None
        self._translating_image_path = ""         # 正在翻译的图片路径（缓存判断用）
        self._translating_page_index = None       # 翻译启动时捕获的页码
        self._is_temp_image = False               # 当前图片是否为临时文件（框选翻译产物，不缓存）
        self._temp_files = []                     # 框选翻译产生的临时文件

    # ===================== 翻译操作 =====================

    def translate_page(self, image_path, context=None, page_index=None):
        """翻译整张图片"""
        self._cancel_worker()              # 先清理上一个 worker
        self._translating_image_path = image_path
        self._translating_page_index = page_index  # 翻译启动时即捕获
        self._is_temp_image = False        # 非临时文件，结果应缓存
        self.translation_started.emit()
        self.translating_changed.emit(True)
        self._start_worker(image_path, context=context)

    def translate_region(self, image_path, region_pixmap, context=None, page_index=None):
        """翻译框选区域：暂存为临时文件 → 启动 Worker"""
        self._cancel_worker()
        try:
            temp_dir = tempfile.gettempdir()
            unique_name = f"bubbletrans_{uuid.uuid4().hex[:8]}.png"
            temp_path = os.path.join(temp_dir, unique_name)
            self._translating_image_path = temp_path
            self._translating_page_index = page_index  # 捕获页码
            self._is_temp_image = True       # 临时文件，不缓存
            region_pixmap.save(temp_path, "PNG")
            self._temp_files.append(temp_path)
            self.translation_started.emit()
            self.translating_changed.emit(True)
            self._start_worker(temp_path, context=context)
        except Exception as e:
            self.translation_error.emit(f"保存临时图片失败: {e}")

    # ===================== 状态查询 =====================

    def is_translating(self):
        return self._worker is not None and self._worker.isRunning()

    # ===================== Worker 生命周期 =====================

    def _start_worker(self, image_path, context=None):
        """创建并启动 TranslationWorker，连接信号"""
        self._worker = TranslationWorker(image_path, context=context)
        self._worker.stage_changed.connect(self._on_stage)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_stage(self, stage):
        self.stage_changed.emit(stage)

    def _on_finished(self, origin_text, translated_text, summary_dict):
        """Worker 完成 → 写缓存 → 发射结果信号"""
        # 写缓存（仅非临时文件，且结果不是来自缓存命中）
        current_path = self._translating_image_path
        if current_path and os.path.exists(current_path) and not llm_engine.last_from_cache:
            if not self._is_temp_image:
                mtime = os.path.getmtime(current_path)
                self._cache.set(current_path, mtime, {
                    "original": origin_text,
                    "translated": translated_text,
                    "summary": summary_dict,
                }, page_index=self._translating_page_index)
                # SQLite 即时落盘，无需显式 save()
        self._translating_image_path = ""
        self._translating_page_index = None
        self._is_temp_image = False
        self.translating_changed.emit(False)
        self.translation_finished.emit(origin_text, translated_text, summary_dict)
        self._clean_temp_files()
        self._cleanup_worker()

    def _on_error(self, error_msg):
        self._translating_image_path = ""
        self._translating_page_index = None
        self._is_temp_image = False
        self.translating_changed.emit(False)
        self.translation_error.emit(error_msg)
        self._cleanup_worker()

    def _cancel_worker(self):
        """先断开信号再终止 worker，防止残留信号"""
        if self._worker is None:
            return
        try:
            self._worker.stage_changed.disconnect()
        except (TypeError, RuntimeError):
            pass
        try:
            self._worker.finished.disconnect()
        except (TypeError, RuntimeError):
            pass
        try:
            self._worker.error.disconnect()
        except (TypeError, RuntimeError):
            pass
        if self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(500)
        self._worker.deleteLater()
        self._worker = None

    def _cleanup_worker(self):
        """翻译完成后清理 worker（不 terminate，让它自然结束）"""
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    def cancel(self):
        """外部取消当前翻译"""
        self._translating_image_path = ""
        self._translating_page_index = None
        self.translating_changed.emit(False)
        self._cancel_worker()
        self._clean_temp_files()

    def shutdown(self):
        """程序退出时终止 worker + 清理临时文件"""
        self._cancel_worker()
        self._clean_temp_files()

    # ===================== 临时文件 =====================

    def _clean_temp_files(self):
        for f in self._temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except OSError:
                pass
        self._temp_files.clear()

    # ===================== 缓存操作 =====================

    def clear_page_cache(self, image_path):
        return self._cache.clear_image(image_path)

    def clear_all_cache(self):
        count = len(self._cache)
        self._cache.clear()
        return count

    def cache_entry_count(self):
        return len(self._cache)
