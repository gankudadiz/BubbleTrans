#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - 后台工作线程

TranslationWorker: 后台 LLM 翻译线程
ImageLoadWorker:  后台图片异步解码线程
"""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QThread, pyqtSignal
from engine.llm import llm_engine


class TranslationWorker(QThread):
    """后台线程：执行 LLM 翻译任务"""

    finished = pyqtSignal(str, str, dict)   # origin_text, translated_text, summary_dict
    error = pyqtSignal(str)                  # error_msg
    status = pyqtSignal(str)                 # （已弃用，保留兼容）
    stage_changed = pyqtSignal(str)          # 阶段变化

    def __init__(self, image_path):
        super().__init__()
        self.image_path = image_path

    def run(self):
        try:
            self.stage_changed.emit("正在翻译…")
            origin_text, translated_text, summary_dict = llm_engine.translate_image(self.image_path)
            self.stage_changed.emit("正在解析…")
            self.finished.emit(origin_text, translated_text, summary_dict)
        except Exception as e:
            self.error.emit(str(e))


class ImageLoadWorker(QThread):
    """后台线程：异步解码图片文件为 QPixmap"""

    loaded = pyqtSignal(str, QPixmap)   # image_path, pixmap
    error = pyqtSignal(str, str)        # image_path, error_msg

    def __init__(self, image_path):
        super().__init__()
        self.image_path = image_path

    def run(self):
        try:
            pixmap = QPixmap(self.image_path)
            if pixmap.isNull():
                self.error.emit(self.image_path, f"无法解码: {self.image_path}")
            else:
                self.loaded.emit(self.image_path, pixmap)
        except Exception as e:
            self.error.emit(self.image_path, str(e))
