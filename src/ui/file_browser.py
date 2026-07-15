#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - 文件浏览器组件

打开文件夹/压缩包、构建文件列表、搜索过滤、最近打开菜单。
"""

import os
import shutil
import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, QToolButton,
    QMenu, QFileDialog, QMessageBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QShortcut, QKeySequence

from utils.config import load_config, save_config, add_recent_folder, save_last_position, get_last_position
import utils.archive as archive

_logger = logging.getLogger("BubbleTrans")


class FileBrowser(QWidget):
    """文件浏览器：打开文件夹/压缩包 + 文件列表 + 搜索过滤 + 最近菜单"""

    source_changed = pyqtSignal(str)    # 来源路径变化（切换文件夹/压缩包时）
    file_selected = pyqtSignal(str)     # 用户点击文件 → 文件完整路径
    file_list_loaded = pyqtSignal()     # 文件列表构建完成

    IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source_path = ""           # 原始来源（目录或压缩包）
        self._current_folder = ""        # 实际图片目录
        self._archive_temp_dir = ""      # 压缩包解压缓存目录（项目 cache/ 下）

        self._build_ui()

    def _build_ui(self):
        """搭建工具栏 + 搜索框 + 文件列表"""
        # 水平方向不主动抢宽度，避免长文件名把左侧侧边栏撑得很宽
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # --- 工具栏按钮：打开文件夹 / 打开压缩包 / 历史记录 ---
        self._open_btn = QToolButton()
        self._open_btn.setText("Open Folder")
        self._open_btn.setToolTip("打开文件夹")
        self._open_btn.clicked.connect(self._open_folder)

        self._archive_btn = QToolButton()
        self._archive_btn.setText("Open Archive")
        self._archive_btn.setToolTip("打开压缩包 (.cbz / .zip / .cbr)")
        self._archive_btn.clicked.connect(self._open_archive)

        self._history_btn = QToolButton()
        self._history_btn.setText("History")
        self._history_btn.setToolTip("最近 / 点击下拉查看最近打开")
        self._history_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        self._history_menu = QMenu(self)
        self._history_btn.setMenu(self._history_menu)
        self._refresh_history_menu()
        self._history_menu.aboutToShow.connect(self._refresh_history_menu)

        # 为左侧面板留出一些内边距，使 focus/hover 边框不会溢出到主图像区域。
        toolbar_layout = QVBoxLayout()
        toolbar_layout.setContentsMargins(6, 6, 6, 6)
        toolbar_layout.setSpacing(0)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.setContentsMargins(0, 0, 0, 0)

        btn_style = """
            QToolButton {
                min-height: 28px;
                padding: 4px 8px;
                border: 1px solid #555555;
                border-radius: 4px;
                background: #333333;
                color: #eeeeee;
            }
            QToolButton:hover {
                background: #3d3d3d;
                border: 1px solid #00bfa5;
            }
            QToolButton:pressed {
                background: #2a2a2a;
            }
            QToolButton:focus {
                outline: none;
                border: 1px solid #00bfa5;
            }
            QToolButton::menu-indicator {
                subcontrol-position: right center;
                subcontrol-origin: padding;
                right: 4px;
                width: 10px;
                height: 10px;
            }
        """
        for btn in (self._open_btn, self._archive_btn, self._history_btn):
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setMinimumHeight(28)
            btn.setStyleSheet(btn_style)
            btn_row.addWidget(btn)

        toolbar_layout.addLayout(btn_row)
        layout.addLayout(toolbar_layout)

        # --- 搜索框 ---
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 搜索文件名…")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.textChanged.connect(self._filter)
        layout.addWidget(self.search_box)

        # --- 文件列表 ---
        self.file_list = QListWidget()
        # 长文件名中间省略，不因内容把面板撑宽
        self.file_list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.file_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.file_list.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.file_list.itemClicked.connect(self._on_file_clicked)
        layout.addWidget(self.file_list)

        # --- 快捷键 ---
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search)
        QShortcut(QKeySequence("Escape"), self.search_box, self._clear_search)

    # ===================== 公开接口 =====================

    @property
    def current_folder(self):
        return self._current_folder

    @property
    def current_source_path(self):
        return self._source_path

    @property
    def current_file_index(self):
        return self.file_list.currentRow()

    def files_count(self):
        return self.file_list.count()

    def current_file_path(self):
        """当前选中文件的完整路径，无选中返回 None"""
        item = self.file_list.currentItem()
        if item:
            return os.path.join(self._current_folder, item.text())
        return None

    def get_file_paths(self):
        """所有图片文件的完整路径列表（保持文件列表顺序）"""
        return [os.path.join(self._current_folder, self.file_list.item(i).text())
                for i in range(self.file_list.count())]

    def navigate(self, delta):
        """
        翻页。跳过隐藏项（搜索过滤结果）。到达边界时返回 None。
        """
        count = self.file_list.count()
        if count == 0:
            return None
        current = self.file_list.currentRow()
        new_row = current
        while True:
            new_row += delta
            if new_row < 0 or new_row >= count:
                return None
            if not self.file_list.item(new_row).isHidden():
                break
        self.file_list.setCurrentRow(new_row)
        return self.current_file_path()

    def restore_last(self):
        """自动恢复上次会话：遍历最近列表，加载第一个存在的路径"""
        cfg = load_config()
        recent = cfg.get("recent_folders", [])
        if not recent:
            return

        for path in recent[:]:
            if os.path.exists(path):
                ext = os.path.splitext(path)[1].lower()
                is_archive = ext in ('.cbz', '.zip', '.cbr')
                self._load_source(path, is_archive)
                return
            else:
                recent.remove(path)

        # 所有路径都不存在，保存更新后的列表
        save_config({"recent_folders": recent})

    def shutdown(self):
        """关闭时保存阅读位置（解压目录保留以便下次复用，不主动清理）"""
        if self._source_path and self.current_file_index >= 0:
            save_last_position(self._source_path, self.current_file_index)
        # 不再调用 _cleanup_archive_temp()：
        # cache/arc_<hash>/ 跨会话保留，供二次打开同一压缩包时复用

    # ===================== 内部：打开来源 =====================

    def _open_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Select Comic Folder")
        if path:
            self._load_source(path, False)

    def _open_archive(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Comic Archive",
            "",
            "Comic Archive (*.cbz *.zip *.cbr)"
        )
        if path:
            self._load_source(path, True)

    def _load_source(self, path, is_archive):
        """统一加载入口"""
        # 保存旧来源的阅读位置
        if self._source_path and self.current_file_index >= 0:
            save_last_position(self._source_path, self.current_file_index)

        # 仅当来源不同时才清理上一个解压目录
        # 同一压缩包再次打开时跳过清理，让 archive 模块走缓存复用
        if path != self._source_path:
            self._cleanup_archive_temp()

        self._source_path = path
        if is_archive:
            archive_name = os.path.basename(path)
            _logger.info(f"_load_source: 解压压缩包 {archive_name}")
            try:
                temp_dir, _image_files = archive.extract_to_temp(path)
                self._archive_temp_dir = temp_dir
                self._current_folder = temp_dir
                _logger.info(f"_load_source: 解压完成 {archive_name}")
            except Exception as e:
                _logger.error(f"_load_source: 解压失败 {archive_name}: {e}")
                QMessageBox.critical(self, "解压失败", f"无法打开压缩包: {e}")
                return
        else:
            _logger.info(f"_load_source: 打开目录 {path}")
            self._current_folder = path

        # 先通知外部清理缓存（避免旧缓存污染新来源）
        self.source_changed.emit(self._source_path)
        # 再构建文件列表并触发首次加载
        self._build_file_list()
        add_recent_folder(self._source_path)

    def _build_file_list(self):
        """扫描目录，构建文件列表，恢复上次阅读位置"""
        self.file_list.clear()
        try:
            files = sorted([
                f for f in os.listdir(self._current_folder)
                if f.lower().endswith(self.IMAGE_EXTENSIONS)
            ])
        except OSError as e:
            _logger.error(f"_build_file_list 失败: {e}")
            QMessageBox.critical(self, "错误", f"无法读取目录: {e}")
            return

        self.file_list.addItems(files)

        # 恢复上次位置
        last_idx = get_last_position(self._source_path)
        if 0 <= last_idx < len(files):
            self.file_list.setCurrentRow(last_idx)
        elif files:
            self.file_list.setCurrentRow(0)

        self.file_list_loaded.emit()

    # ===================== 内部：搜索过滤 =====================

    def _filter(self, query):
        q = query.strip().lower()
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            item.setHidden(q not in item.text().lower() if q else False)

    def _focus_search(self):
        self.search_box.setFocus()
        self.search_box.selectAll()

    def _clear_search(self):
        self.search_box.clear()
        self.file_list.setFocus()

    # ===================== 内部：文件点击 =====================

    def _on_file_clicked(self, item):
        path = os.path.join(self._current_folder, item.text())
        self.file_selected.emit(path)

    # ===================== 内部：历史菜单 =====================

    def _refresh_history_menu(self):
        """刷新 History 按钮下拉菜单：最近记录 + 清除历史"""
        self._history_menu.clear()

        cfg = load_config()
        recent = cfg.get("recent_folders", [])
        if not recent:
            empty_action = self._history_menu.addAction("（无最近记录）")
            empty_action.setEnabled(False)
        else:
            for p in recent:
                display = self._truncate_path(p)
                action = self._history_menu.addAction(display)
                action.setToolTip(p)
                # pylint: disable=cell-var-from-loop
                action.triggered.connect(lambda checked, path=p: self._open_recent(path))

        self._history_menu.addSeparator()
        clear_action = self._history_menu.addAction("清除历史")
        clear_action.triggered.connect(self._clear_recent)

    @staticmethod
    def _truncate_path(path, max_len=60):
        if len(path) <= max_len:
            return path
        half = (max_len - 3) // 2
        return path[:half] + "..." + path[-half:]

    def _open_recent(self, path):
        if not os.path.exists(path):
            QMessageBox.warning(self, "路径无效", f"路径不存在:\n{path}")
            cfg = load_config()
            recent = cfg.get("recent_folders", [])
            if path in recent:
                recent.remove(path)
                save_config({"recent_folders": recent})
                self._refresh_history_menu()
            return
        ext = os.path.splitext(path)[1].lower()
        is_archive = ext in ('.cbz', '.zip', '.cbr')
        self._load_source(path, is_archive)

    def _clear_recent(self):
        save_config({"recent_folders": []})
        self._refresh_history_menu()

    # ===================== 内部：清理 =====================

    def _cleanup_archive_temp(self):
        """清理上一个压缩包的解压缓存目录（切换来源时调用，shutdown 不调用）"""
        if self._archive_temp_dir and os.path.exists(self._archive_temp_dir):
            _logger.info(f"_cleanup_archive_temp: 清理缓存目录 {self._archive_temp_dir}")
            try:
                shutil.rmtree(self._archive_temp_dir, ignore_errors=True)
            except Exception as e:
                _logger.warning(f"_cleanup_archive_temp: 清理失败 {e}")
            self._archive_temp_dir = ""
