#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - Scrappy Comic Translator 主窗口模块

本模块实现了漫画翻译器的主窗口界面，包含以下功能：
1. 文件浏览 - 左侧面板显示漫画文件夹中的图片文件
2. 图片画布 - 中间面板显示图片，支持框选翻译区域
3. 翻译面板 - 右侧面板显示原文和译文
4. 工具栏 - 包含打开文件夹、设置等基本功能

核心组件：
- MainWindow: 主窗口类，管理整个应用程序的UI
- TranslationWorker: 后台线程（定义在 engine/workers.py）
- CropConfirmDialog: 确认框选区域的对话框
"""

# ============================================================================
# PyQt6 框架导入
# ============================================================================
# PyQt6是Qt框架的Python绑定，提供丰富的GUI组件
# 这里从三个模块导入所需组件：
#   QtWidgets: 窗口部件（按钮、文本框、列表等）
#   QtGui:    图形相关（图标、图片处理等）
#   QtCore:   核心功能（线程、信号、定时器等）
# ============================================================================
from PyQt6.QtWidgets import (
    QMainWindow,       # 主窗口基类
    QWidget,           # 通用窗口部件
    QHBoxLayout,       # 水平布局管理器
    QVBoxLayout,       # 垂直布局管理器
    QLabel,            # 标签，显示文本
    QPushButton,       # 按钮
    QListWidget,       # 列表控件，显示文件列表
    QTextEdit,         # 多行文本编辑框
    QSplitter,         # 可分割的窗口组件
    QFileDialog,       # 文件夹选择对话框
    QToolBar,          # 工具栏
    QToolButton,       # 工具按钮（支持下拉菜单）
    QStatusBar,        # 状态栏
    QMessageBox,       # 消息对话框
    QApplication,      # 应用程序对象（用于获取屏幕信息）
    QDialog,           # 对话框基类
    QDialogButtonBox,  # 按钮盒（确定/取消按钮组）
    QFrame,            # 框架容器（骨架屏占位块）
    QCheckBox,         # 复选框
    QLineEdit,         # 单行文本输入框（搜索框）
    QMenu,             # 弹出菜单
    QProgressBar,      # 进度条
    QSpinBox,          # 数字调节框（批量翻译范围选择）
)

from PyQt6.QtGui import (
    QAction,           # 动作（可绑定到工具栏按钮）
    QIcon,             # 图标
    QPixmap,           # 图片对象，用于显示图像
    QKeySequence,      # 快捷键序列（QShortcut 绑定用）
    QShortcut,         # 快捷键绑定（Ctrl+F / Esc）
)

from PyQt6.QtCore import (
    Qt,                # 常量定义（如对齐方式）
    QThread,           # 线程基类
    pyqtSignal,        # 信号定义（线程间通信）
    QTimer,            # 定时器（按钮动画）
    QPropertyAnimation,# 属性动画（骨架屏脉冲）
)

# ============================================================================
# 标准库导入
# ============================================================================
import os               # 文件路径操作
import re               # 正则表达式
import shutil           # 文件操作（删除目录树）
import zipfile          # ZIP 格式校验
import time             # 耗时统计
import logging          # 日志记录
_logger = logging.getLogger("BubbleTrans")

# ============================================================================
# 项目内部模块导入
# ============================================================================
# 这些模块位于项目的ui和engine目录中
# canvas.py:   图片画布组件，负责显示图片和处理框选
# settings.py: 设置对话框
# llm.py:      大语言模型翻译引擎
# ============================================================================
from ui.canvas import ImageCanvas
from ui.settings import SettingsDialog
from engine.llm import llm_engine
from utils.cache import TranslationCache
import utils.archive as archive  # 压缩包支持
from utils.config import load_config, save_config, add_recent_folder, save_last_position, get_last_position
from ui.prefetch import PrefetchManager
from engine.workers import TranslationWorker, ImageLoadWorker
from ui.image_cache import ImageCacheManager
from engine.translation_controller import TranslationController
from ui.file_browser import FileBrowser
from ui.batch import BatchTranslationManager

# 批量翻译耗时提示参数
BATCH_TIME_THRESHOLD = 15       # 超过此页数弹出耗时提示
PAGE_AVG_TIME_SEC = 8           # 单页平均耗时（秒，含 API 往返）


# ============================================================================
# CropConfirmDialog 类 - 框选确认对话框
# ============================================================================
# 当用户在图片上框选一个区域后，弹出此对话框让用户确认
# 显示选区的预览图，用户可以选择确认或取消
# ============================================================================
class CropConfirmDialog(QDialog):
    """
    框选区域确认对话框
    
    用途：在执行OCR/翻译之前，让用户确认框选的区域是否正确
    """
    
    def __init__(self, pixmap: QPixmap, parent=None):
        """
        初始化对话框
        
        参数:
            pixmap: 框选的图片区域（QPixmap格式）
            parent: 父窗口
        """
        super().__init__(parent)
        self.setWindowTitle("确认截图")
        self.setModal(True)  # 设置为模态对话框（显示时阻塞其他窗口）
        
        # 创建垂直布局
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("确认使用该选区进行翻译吗？"))
        
        # 创建预览标签
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)  # 居中显示
        self.preview_label.setMinimumSize(360, 240)  # 设置最小尺寸
        self.preview_label.setPixmap(
            pixmap.scaled(
                720,  # 目标宽度
                480,  # 目标高度
                Qt.AspectRatioMode.KeepAspectRatio,  # 保持宽高比
                Qt.TransformationMode.SmoothTransformation,  # 平滑变换
            )
        )
        layout.addWidget(self.preview_label)
        
        # 创建按钮盒（确定和取消按钮）
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        # 设置按钮文字为中文
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确认")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        # 连接按钮信号到对话框的accept/reject槽
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


# ============================================================================
# ShortcutOverlay 类 - 首次启动快捷键引导浮层
# ============================================================================
class ShortcutOverlay(QDialog):
    """首次启动时的快捷键引导浮层 — 半透明遮罩 + 居中暗色卡片"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("快捷键指南")
        self.setModal(True)

        # 无边框 + 透明背景（用于实现圆角遮罩效果）
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # 暗色卡片容器
        card = QFrame()
        card.setObjectName("shortcutCard")
        card.setStyleSheet("""
            QFrame#shortcutCard {
                background-color: #2b2b2b;
                border: 1px solid #555;
                border-radius: 10px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(12)

        # 标题
        title = QLabel("⌨ 快捷键指南")
        title.setStyleSheet("color: #ffffff; font-size: 16px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)

        # 快捷键表格（用 QLabel 模拟）
        shortcuts_text = """
        <table style="color:#cccccc; font-size:13px; width:100%%; border-spacing:8px;">
        <tr><td style="color:#8ab4f8;">← →</td><td>上一页 / 下一页</td></tr>
        <tr><td style="color:#8ab4f8;">右键拖拽</td><td>框选翻译区域</td></tr>
        <tr><td style="color:#8ab4f8;">滚轮</td><td>缩放图片</td></tr>
        <tr><td style="color:#8ab4f8;">Esc</td><td>取消框选</td></tr>
        <tr><td style="color:#8ab4f8;">F5</td><td>翻译当前页</td></tr>
        </table>
        """
        shortcuts_label = QLabel(shortcuts_text)
        shortcuts_label.setTextFormat(Qt.TextFormat.RichText)
        shortcuts_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(shortcuts_label)

        # "不再提示"复选框
        self.dont_show_check = QCheckBox("不再提示")
        self.dont_show_check.setStyleSheet("color: #999; font-size: 12px;")
        card_layout.addWidget(self.dont_show_check, alignment=Qt.AlignmentFlag.AlignCenter)

        # 关闭按钮
        close_btn = QPushButton("知道了")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a7bd5;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 32px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #4a8be5;
            }
            QPushButton:pressed {
                background-color: #2a6bc5;
            }
        """)
        close_btn.clicked.connect(self.accept)
        card_layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(card)

    def should_not_show_again(self) -> bool:
        """返回用户是否勾选了"不再提示" """
        return self.dont_show_check.isChecked()


# ============================================================================
# MainWindow 类 - 主窗口
# ============================================================================
# 应用程序的主窗口，继承自QMainWindow
# 
# 窗口布局（从左到右）：
# ┌─────────┬─────────────────────┬────────────────┐
# │ 文件列表 │      图片画布        │   翻译面板     │
# │(200px)  │    (自适应扩展)      │    (400px)    │
# └─────────┴─────────────────────┴────────────────┘
#
# 工具栏：包含打开文件夹、设置按钮
# 状态栏：显示当前状态信息
# ============================================================================
class MainWindow(QMainWindow):
    """
    主窗口类 - BubbleTrans漫画翻译器的主界面
    
    功能：
    - 左侧面板：显示漫画文件夹中的图片文件列表
    - 中间面板：显示当前选中的图片，支持框选翻译区域
    - 右侧面板：显示原文和译文
    - 工具栏：常用操作按钮
    - 状态栏：显示当前状态
    """
    
    def __init__(self):
        """初始化主窗口"""
        super().__init__()
        self.setWindowTitle("BubbleTrans - Scrappy Comic Translator")
        self.resize(1200, 800)  # 设置窗口大小
        
        # 实例变量初始化
        
        # 右侧面板状态
        self.origin_text = ""         # 当前原文
        self.translated_text = ""     # 当前译文
        self.current_tab = "trans"    # 当前选中的 tab（默认译文）
        
        # === 图片缓存与异步加载 ===
        self.current_file_index = -1        # 当前显示的文件在列表中的索引
        # 图片缓存管理器（LRU + 异步解码 + 预加载）
        self.image_cache = ImageCacheManager(max_cache_size=10, prefetch_range=2, parent=self)
        self.image_cache.image_loaded.connect(self._on_image_cached)
        self.image_cache.image_error.connect(self._on_image_cache_error)
        
        # 初始化翻译缓存（注入到全局 llm_engine 实例）
        self.translation_cache = TranslationCache()
        llm_engine.cache = self.translation_cache

        # 翻译编排控制器
        self.translation_controller = TranslationController(self.translation_cache, parent=self)
        self.translation_controller.stage_changed.connect(self._on_translation_stage)
        self.translation_controller.translating_changed.connect(self._set_translating)
        self.translation_controller.translation_finished.connect(self._on_translation_finished)
        self.translation_controller.translation_error.connect(self._on_translation_error)
        self.translation_controller.translation_started.connect(self._on_translation_started)

        # === 预翻译管理器 ===
        _cfg = load_config()
        self.prefetch_manager = PrefetchManager(
            self.translation_cache,
            max_concurrent=_cfg.get("prefetch_concurrent", 2),
        )
        self.prefetch_manager.progress_changed.connect(self._on_prefetch_progress)
        self.prefetch_manager.page_completed.connect(self._on_prefetch_page_completed)
        self.prefetch_manager.all_completed.connect(self._on_prefetch_all_completed)

        # === 批量翻译管理器 ===
        self.batch_manager = BatchTranslationManager(self.translation_cache, max_concurrent=2, parent=self)
        self.batch_manager.progress_updated.connect(self._on_batch_progress)
        self.batch_manager.batch_finished.connect(self._on_batch_finished)

        # 文件浏览器（替代原来的左侧面板）
        self.file_browser = FileBrowser()
        self.file_browser.file_selected.connect(self.load_image)
        self.file_browser.source_changed.connect(self._on_source_changed)
        self.file_browser.file_list_loaded.connect(self._on_file_list_loaded)

        # === 翻译进度动画 ===
        # 按钮加载动画：3 点省略号循环
        self._spinner_dots = 0
        self._spinner_timer = QTimer()
        self._spinner_timer.timeout.connect(self._update_spinner)
        # 骨架屏脉冲动画
        self._skeleton_pulse = None

        # 初始化UI
        self.init_ui()

        # 首次启动：延迟弹出快捷键引导浮层（等窗口完整渲染后再弹）
        QTimer.singleShot(500, self._maybe_show_shortcut_overlay)

        # 自动恢复上次打开的文件（延迟以确保窗口已初始化）
        QTimer.singleShot(100, self.file_browser.restore_last)
    
    def init_ui(self):
        """
        初始化用户界面
        
        创建并布局所有UI组件：
        1. 工具栏
        2. 主布局（三栏：文件列表、图片画布、翻译面板）
        3. 状态栏
        """
        # ===== 工具栏 =====
        toolbar = QToolBar()
        self.addToolBar(toolbar)

        # "快捷键"说明按钮
        shortcuts_action = QAction("Shortcuts", self)
        shortcuts_action.triggered.connect(self._show_shortcut_overlay)
        toolbar.addAction(shortcuts_action)

        # "设置"按钮
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.open_settings)
        settings_action.setToolTip("设置 (快捷键、API 配置)")
        toolbar.addAction(settings_action)

        # ===== 主布局 =====
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # --- 1. 左侧面板（FileBrowser 替代）---
        splitter.addWidget(self.file_browser)
        
        # --- 2. 图片画布（中间，自适应扩展）---
        self.canvas = ImageCanvas()
        self.canvas.region_selected.connect(self.handle_region_selected)  # 框选完成时触发
        self.canvas.nav_prev.connect(self._nav_prev_page)                 # ← 前翻页
        self.canvas.nav_next.connect(self._nav_next_page)                 # → 后翻页
        splitter.addWidget(self.canvas)
        
        # --- 3. 翻译面板（右侧，固定宽度300px）---
        right_panel = QWidget()
        right_panel.setFixedWidth(300)
        right_layout = QVBoxLayout(right_panel)
        
        # --- 按钮行（两行：主操作 + 辅助信息）---
        # 第一行：主操作按钮，有充足空间不截断
        tool_row1 = QHBoxLayout()
        tool_row1.setSpacing(6)
        self.translate_page_btn = QPushButton("翻译当前页")
        self.translate_page_btn.clicked.connect(self.translate_current_page)
        tool_row1.addWidget(self.translate_page_btn)
        # 预翻译下拉按钮
        self.prefetch_btn = QToolButton()
        self.prefetch_btn.setText("预翻译")  # QToolButton 原生下拉箭头自动显示
        self.prefetch_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        prefetch_menu = QMenu(self)
        for n in (1, 3, 5):
            action = prefetch_menu.addAction(f"下 {n} 页")
            action.setData(n)
            action.triggered.connect(lambda checked, count=n: self._manual_prefetch(count))
        prefetch_menu.addSeparator()
        batch_action = prefetch_menu.addAction("批量翻译...")
        batch_action.triggered.connect(self._show_batch_dialog)
        self.prefetch_btn.setMenu(prefetch_menu)
        tool_row1.addWidget(self.prefetch_btn)
        tool_row1.addStretch()
        right_layout.addLayout(tool_row1)
        # 第二行：次要操作 + 语言信息
        tool_row2 = QHBoxLayout()
        tool_row2.setSpacing(6)
        # 清除缓存下拉按钮
        self.clear_cache_btn = QToolButton()
        self.clear_cache_btn.setText("清除缓存")
        self.clear_cache_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.clear_cache_btn.setStyleSheet("QToolButton { color: #888; font-size: 11px; padding: 2px 8px; }")
        clear_menu = QMenu(self)
        clear_current_action = clear_menu.addAction("清除当前页缓存")
        clear_current_action.triggered.connect(self._clear_current_page_cache)
        clear_all_action = clear_menu.addAction("清除全部缓存")
        clear_all_action.triggered.connect(self._clear_translation_cache)
        self.clear_cache_btn.setMenu(clear_menu)
        tool_row2.addWidget(self.clear_cache_btn)
        tool_row2.addStretch()
        self.lang_label = QLabel(f"语言: {llm_engine.target_lang}")
        self.lang_label.setStyleSheet("color: #aaa; font-size: 11px;")
        tool_row2.addWidget(self.lang_label)
        right_layout.addLayout(tool_row2)
        
        # --- 分段切换按钮："原文" / "译文" ---
        seg_container = QWidget()
        seg_container.setObjectName("segContainer")
        seg_container.setStyleSheet("""
            QWidget#segContainer {
                background-color: #1e1e1e;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 1px;
            }
        """)
        seg_layout = QHBoxLayout(seg_container)
        seg_layout.setContentsMargins(0, 0, 0, 0)
        seg_layout.setSpacing(0)
        
        self.btn_origin_seg = QPushButton("原文")
        self.btn_trans_seg = QPushButton("译文")
        self.btn_origin_seg.setCheckable(True)
        self.btn_trans_seg.setCheckable(True)
        
        # 分段按钮样式（选中 / 未选中 / hover）
        seg_btn_style = """
            QPushButton {
                background-color: transparent;
                color: #999999;
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 4px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2b2b2b;
            }
            QPushButton:checked {
                background-color: #3a3a3a;
                color: #ffffff;
                border: 1px solid #555;
            }
        """
        self.btn_origin_seg.setStyleSheet(seg_btn_style)
        self.btn_trans_seg.setStyleSheet(seg_btn_style)
        
        self.btn_origin_seg.clicked.connect(lambda: self._switch_tab("origin"))
        self.btn_trans_seg.clicked.connect(lambda: self._switch_tab("trans"))
        
        seg_layout.addWidget(self.btn_origin_seg)
        seg_layout.addWidget(self.btn_trans_seg)
        right_layout.addWidget(seg_container)
        
        # --- QSplitter（垂直方向，分割共享文本区和总结区）---
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # --- 共享文本区 ---
        self.shared_text_edit = QTextEdit()
        self.shared_text_edit.setReadOnly(True)
        self.shared_text_edit.setPlaceholderText("请先点击「翻译当前页」或框选区域进行翻译")
        self.right_splitter.addWidget(self.shared_text_edit)
        
        # --- 总结区 ---
        summary_widget = QWidget()
        summary_layout = QVBoxLayout(summary_widget)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        
        self.summary_label = QLabel("▼ 当页总结")
        summary_layout.addWidget(self.summary_label)
        self.summary_text_edit = QTextEdit()
        self.summary_text_edit.setReadOnly(True)
        self.summary_text_edit.setPlaceholderText("翻译后将自动生成当页剧情总结和翻译备注")
        summary_layout.addWidget(self.summary_text_edit)
        
        self.right_splitter.addWidget(summary_widget)
        
        right_layout.addWidget(self.right_splitter)
        
        # --- 批量翻译进度 UI（默认隐藏）---
        self.batch_progress_frame = QFrame()
        self.batch_progress_frame.setObjectName("batchProgressFrame")
        batch_layout = QVBoxLayout(self.batch_progress_frame)
        batch_layout.setContentsMargins(0, 4, 0, 0)

        # 进度条行
        progress_row = QHBoxLayout()
        self.batch_progress_bar = QProgressBar()
        self.batch_progress_bar.setTextVisible(False)
        self.batch_progress_bar.setFixedHeight(6)
        progress_row.addWidget(self.batch_progress_bar, 1)
        self.batch_progress_label = QLabel("")
        self.batch_progress_label.setStyleSheet("color: #aaa; font-size: 11px;")
        progress_row.addWidget(self.batch_progress_label)
        batch_layout.addLayout(progress_row)

        # 按钮行
        btn_row = QHBoxLayout()
        self.batch_pause_btn = QPushButton("暂停")
        self.batch_pause_btn.setFixedWidth(60)
        self.batch_pause_btn.clicked.connect(self._on_batch_pause_resume)
        self.batch_cancel_btn = QPushButton("取消")
        self.batch_cancel_btn.setFixedWidth(60)
        self.batch_cancel_btn.clicked.connect(self._on_batch_cancel)
        btn_row.addStretch()
        btn_row.addWidget(self.batch_pause_btn)
        btn_row.addWidget(self.batch_cancel_btn)
        batch_layout.addLayout(btn_row)

        self.batch_progress_frame.hide()
        right_layout.addWidget(self.batch_progress_frame)

        # --- 骨架屏（翻译等待时覆盖文本区域）---
        self.skeleton_widget = self._create_skeleton()
        right_layout.addWidget(self.skeleton_widget)
        
        splitter.addWidget(right_panel)
        
        # 设置分割器初始比例：[200, 600, 300]
        splitter.setSizes([200, 600, 300])
        
        # 默认选中"译文" tab
        self._switch_tab("trans")
        
        # ===== 状态栏 =====
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("BubbleTrans v2.0 - 就绪")
        # 状态栏右侧常驻快捷键提示
        shortcut_hint_label = QLabel("← → 翻页 | 右键框选 | 滚轮缩放")
        shortcut_hint_label.setStyleSheet("color: #777; font-size: 11px; padding-right: 8px;")
        self.status_bar.addPermanentWidget(shortcut_hint_label)
    
    # ===================== 首次启动引导 =====================
    
    def _maybe_show_shortcut_overlay(self):
        """如果用户从未看过快捷键引导，则弹出 ShortcutOverlay"""
        config = load_config()
        if config.get("shortcut_hint_shown"):
            return
        overlay = ShortcutOverlay(self)
        overlay.exec()
        if overlay.should_not_show_again():
            save_config({"shortcut_hint_shown": True})

    def _show_shortcut_overlay(self):
        """手动触发快捷键引导浮层（工具栏按钮）"""
        overlay = ShortcutOverlay(self)
        overlay.exec()

    def _on_source_changed(self, source_path):
        """来源切换 → 清空图片缓存 + 清空预翻译队列 + 更新标题"""
        self.image_cache.clear()
        self.prefetch_manager.clear()
        self.setWindowTitle(f"BubbleTrans - {os.path.basename(source_path)}")

    def _on_file_list_loaded(self):
        """文件列表构建完成 → 触发首次图片加载"""
        path = self.file_browser.current_file_path()
        if path:
            self.load_image(path)
    
    # ===================== 翻译进度辅助方法 =====================
    
    def _create_skeleton(self):
        """创建右侧面板骨架屏（翻译等待时的灰色占位块）"""
        widget = QWidget()
        widget.setObjectName("skeletonWidget")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        bar_style = "background-color: #3a3a3a; border-radius: 3px;"

        # 上半部分 —— 模拟多条文本行（不同宽度模拟真实排版）
        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(6)
        for w_pct in (0.95, 0.88, 0.72, 0.93, 0.65, 0.85):
            bar = QFrame()
            bar.setStyleSheet(bar_style)
            bar.setFixedHeight(12)
            # 用 stretch + dummy 控制宽度比例
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            bar.setFixedWidth(int(290 * w_pct))
            row.addWidget(bar)
            row.addStretch()
            row_wrapper = QWidget()
            row_wrapper.setLayout(row)
            top_layout.addWidget(row_wrapper)
        top_layout.addStretch()
        layout.addWidget(top, 2)

        # 分割线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #444;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # 下半部分 —— 模拟总结区
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 4, 0, 0)
        bottom_layout.setSpacing(6)

        title = QFrame()
        title.setStyleSheet(bar_style)
        title.setFixedHeight(14)
        title.setFixedWidth(80)
        bottom_layout.addWidget(title)

        for w_pct in (0.90, 0.75, 0.60):
            bar = QFrame()
            bar.setStyleSheet(bar_style)
            bar.setFixedHeight(12)
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            bar.setFixedWidth(int(290 * w_pct))
            row.addWidget(bar)
            row.addStretch()
            row_wrapper = QWidget()
            row_wrapper.setLayout(row)
            bottom_layout.addWidget(row_wrapper)
        bottom_layout.addStretch()
        layout.addWidget(bottom, 1)

        widget.hide()
        return widget

    def _show_skeleton(self, visible):
        """切换骨架屏与文本区域的可见性"""
        self.skeleton_widget.setVisible(visible)
        self.right_splitter.setVisible(not visible)

    def _start_skeleton_pulse(self):
        """骨架屏脉冲动画"""
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        if self._skeleton_pulse is None:
            effect = QGraphicsOpacityEffect(self.skeleton_widget)
            self.skeleton_widget.setGraphicsEffect(effect)
            self._skeleton_pulse = QPropertyAnimation(effect, b"opacity")
            self._skeleton_pulse.setDuration(1000)
            self._skeleton_pulse.setStartValue(0.35)
            self._skeleton_pulse.setEndValue(0.85)
            self._skeleton_pulse.setLoopCount(-1)  # 无限循环
        self._skeleton_pulse.start()

    def _stop_skeleton_pulse(self):
        """停止骨架屏脉冲动画"""
        if self._skeleton_pulse:
            self._skeleton_pulse.stop()

    def _update_spinner(self):
        """按钮加载动画：省略号循环（.  ..  ...）"""
        self._spinner_dots = (self._spinner_dots + 1) % 4
        dots = "." * self._spinner_dots
        self.translate_page_btn.setText(f"翻译中{dots}")

    def _clear_current_page_cache(self):
        """清除当前页的翻译缓存（无确认，即时清除）"""
        if not self.canvas.current_image_path:
            self.status_bar.showMessage("当前无图片，无法清除缓存", 3000)
            return
        image_path = self.canvas.current_image_path
        removed = self.translation_controller.clear_page_cache(image_path)
        if removed:
            self.origin_text = ""
            self.translated_text = ""
            self.shared_text_edit.clear()
            self.summary_text_edit.clear()
            # 清除后刷新左下角标识，避免仍显示「翻译已缓存」
            self.status_bar.showMessage(
                self._file_status_message("已清除缓存", image_path), 3000
            )
        else:
            self.status_bar.showMessage("当前页无缓存", 3000)

    def _clear_translation_cache(self):
        """清除全部翻译缓存（带确认对话框）"""
        count = self.translation_controller.cache_entry_count()
        if count == 0:
            self.status_bar.showMessage("缓存为空，无需清除", 3000)
            return
        reply = QMessageBox.question(
            self, "清除翻译缓存",
            f"当前共有 {count} 条翻译缓存。\n清除后需要重新翻译所有页面。\n\n确定清除吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.translation_controller.clear_all_cache()
            self.origin_text = ""
            self.translated_text = ""
            self.shared_text_edit.clear()
            self.summary_text_edit.clear()
            current_path = self.canvas.current_image_path
            if current_path:
                self.status_bar.showMessage(
                    self._file_status_message(f"已清除全部缓存({count})", current_path), 5000
                )
            else:
                self.status_bar.showMessage(f"已清除 {count} 条翻译缓存", 5000)

    # ===================== 槽函数 =====================


    
    def load_image(self, file_path: str):
        """加载指定路径的图片（由 file_selected 信号或键盘翻页驱动）"""
        self.current_file_index = self.file_browser.current_file_index
        self._update_page_info()

        pixmap = self.image_cache.get(file_path)
        if pixmap is not None:
            self.canvas.load_image(file_path, pixmap=pixmap)
            self.status_bar.showMessage(self._file_status_message("选中", file_path))
            self._update_page_info()
            self._set_translating(False)
            self._prefetch_adjacent()
            self._trigger_auto_prefetch()
            return

        self.canvas.show_placeholder("加载中…")
        self.status_bar.showMessage(self._file_status_message("加载中", file_path, loading=True))
        self._set_translating(False)
        self.image_cache.load_async(file_path)

    def _has_translation_cache(self, file_path: str) -> bool:
        """当前图片是否已有有效翻译缓存"""
        try:
            mtime = os.path.getmtime(file_path)
            return self.translation_cache.has(file_path, mtime)
        except OSError:
            return False

    def _file_status_message(self, prefix: str, file_path: str, loading: bool = False) -> str:
        """构建左下角状态栏文件信息；有翻译缓存时附加标识"""
        name = os.path.basename(file_path)
        suffix = "…" if loading else ""
        if self._has_translation_cache(file_path):
            return f"{prefix}: {name}（翻译已缓存）{suffix}"
        return f"{prefix}: {name}{suffix}"

    def _on_image_cached(self, image_path, pixmap):
        """图片异步解码完成 → 判断是否仍为当前页 → 渲染"""
        current_item = self.file_browser.file_list.currentItem()
        if current_item:
            current_path = os.path.join(self.file_browser.current_folder, current_item.text())
            if image_path == current_path:
                self.canvas.load_image(image_path, pixmap=pixmap)
                self.status_bar.showMessage(self._file_status_message("已加载", image_path))
                self._update_page_info()
                self._prefetch_adjacent()
                self._trigger_auto_prefetch()

    def _on_image_cache_error(self, image_path, error_msg):
        """图片异步解码失败 → 判断是否仍为当前页 → 提示"""
        current_item = self.file_browser.file_list.currentItem()
        if current_item:
            current_path = os.path.join(self.file_browser.current_folder, current_item.text())
            if image_path == current_path:
                self.canvas.show_placeholder(f"加载失败: {error_msg}")
                self.status_bar.showMessage(f"错误: {error_msg}")

    def _prefetch_adjacent(self):
        """计算相邻页路径，交给 ImageCacheManager 后台预加载"""
        if self.current_file_index < 0:
            return
        total = self.file_browser.files_count()
        paths = []
        for offset in range(1, self.image_cache.prefetch_range + 1):
            for idx in (self.current_file_index + offset, self.current_file_index - offset):
                if 0 <= idx < total:
                    paths.append(os.path.join(self.file_browser.current_folder,
                                              self.file_browser.file_list.item(idx).text()))
        if paths:
            self.image_cache.prefetch(paths)

    def _clear_image_cache(self):
        """清空图片缓存（切换来源时调用）"""
        self.image_cache.clear()
        self.current_file_index = -1
        self.canvas._hide_nav_overlay()

    # ===================== 页面导航 =====================

    def _nav_prev_page(self):
        """← 前翻页（由画布箭头按钮或键盘左方向键触发）"""
        self._navigate_page(-1)

    def _nav_next_page(self):
        """→ 后翻页（由画布箭头按钮或键盘右方向键触发）"""
        self._navigate_page(1)

    def _navigate_page(self, delta: int):
        """执行翻页：修改文件列表选中项并触发图片加载"""
        path = self.file_browser.navigate(delta)
        if path:
            self.load_image(path)

    def _update_page_info(self):
        """刷新画布上的页码指示器和按钮可用状态"""
        count = self.file_browser.files_count()
        if count == 0:
            return
        current = self.file_browser.current_file_index
        if current >= 0:
            self.canvas.update_page_indicator(current + 1, count)
        if self.canvas._btn_prev is not None and self.canvas._btn_next is not None:
            self.canvas._btn_prev.setEnabled(current > 0)
            self.canvas._btn_next.setEnabled(current < count - 1)
        if hasattr(self, 'prefetch_btn'):
            self.prefetch_btn.setEnabled(count > 1 and current < count - 1)

    # ===================== 设置对话框 =====================

    def open_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    # ===================== 分段切换 =====================

    def _switch_tab(self, tab):
        self.current_tab = tab
        self.btn_origin_seg.setChecked(tab == "origin")
        self.btn_trans_seg.setChecked(tab == "trans")
        text = self.origin_text if tab == "origin" else self.translated_text
        self.shared_text_edit.setText(text if text else "")

    # ===================== 翻译回调 =====================

    def handle_region_selected(self, pixmap: QPixmap):
        """处理框选区域完成事件"""
        self.status_bar.showMessage("已选中区域，等待确认...", 3000)
        dlg = CropConfirmDialog(pixmap, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            self.status_bar.showMessage("已取消本次选区", 3000)
            return
        image_path = self.canvas.current_image_path or ""
        self.translation_controller.translate_region(image_path, pixmap, page_index=self.current_file_index)

    def _on_translation_stage(self, stage: str):
        self.status_bar.showMessage(stage)

    def _on_translation_started(self):
        self.origin_text = ""
        self.translated_text = ""
        self.shared_text_edit.clear()
        self.status_bar.showMessage("翻译中...")

    def _on_translation_finished(self, origin_text, translated_text, summary_dict):
        self.origin_text = origin_text
        self.translated_text = translated_text
        self._switch_tab("trans")
        self._fill_summary(summary_dict)
        self.status_bar.showMessage("翻译完成", 5000)

    def _fill_summary(self, summary_dict):
        if summary_dict and (summary_dict.get("plot") or summary_dict.get("notes")):
            plot = summary_dict.get("plot", "").strip()
            notes = summary_dict.get("notes", "").strip()
            html_parts = []
            if plot:
                html_parts.append("📖 剧情")
                html_parts.append("<br><br>")
                html_parts.append(plot.replace('\n', '<br>'))
            if notes:
                if plot:
                    html_parts.append("<br><br>")
                html_parts.append("📝 翻译备注")
                html_parts.append("<br><br>")
                notes_html = notes.replace('\n', '<br>')
                notes_html = re.sub(r'\s+-\s+', '<br>- ', notes_html)
                html_parts.append(notes_html)
            self.summary_text_edit.setHtml("".join(html_parts))
        else:
            self.summary_text_edit.setPlainText("本页暂未生成总结")

    def _on_translation_error(self, error_msg):
        self.status_bar.showMessage(f"错误: {error_msg}")
        QMessageBox.warning(self, "翻译失败", error_msg)

    def _set_translating(self, active: bool):
        self.translate_page_btn.setEnabled(not active)
        if active:
            self._spinner_dots = 0
            self._spinner_timer.start(500)
            self._show_skeleton(True)
            self._start_skeleton_pulse()
        else:
            self._spinner_timer.stop()
            self.translate_page_btn.setText("翻译当前页")
            self._show_skeleton(False)
            self._stop_skeleton_pulse()

    def _manual_prefetch(self, count: int):
        """手动预翻译：将后续 count 页加入预翻译队列（不含当前页）"""
        total = self.file_browser.files_count()
        start = self.current_file_index + 1
        end = min(start + count, total)
        if start >= total:
            return
        paths = []
        for i in range(start, end):
            item = self.file_browser.file_list.item(i)
            if item:
                paths.append(os.path.join(self.file_browser.current_folder, item.text()))
        if paths:
            self.prefetch_manager.enqueue(paths)
            self.status_bar.showMessage(f"📦 预翻译: 已加入 {len(paths)} 页")
            self.prefetch_btn.setText("预翻译中…")

    def _trigger_auto_prefetch(self):
        """自动预翻译触发：读取配置，如开启则调用 resync"""
        config = load_config()
        if not config.get("prefetch_enabled", False):
            return
        total = self.file_browser.files_count()
        if self.current_file_index < 0 or total == 0:
            return
        page_paths = self.file_browser.get_file_paths()
        prefetch_count = config.get("prefetch_count", 3)
        self.prefetch_manager.resync(self.current_file_index, page_paths, prefetch_count)

    def _on_prefetch_progress(self, completed: int, total: int):
        """预翻译进度更新 → 状态栏"""
        self.status_bar.showMessage(f"📦 预翻译: {completed}/{total} 页已完成")

    def _on_prefetch_page_completed(self, image_path: str):
        """预翻译单页完成 → 如果当前正显示该页，刷新 UI 面板"""
        if not self.canvas.current_image_path:
            return
        if image_path != self.canvas.current_image_path:
            return

        # 如果主翻译正在处理同一页，让主翻译的回调来刷新 UI，避免重复刷新
        if self.translation_controller.is_translating():
            return

        # 从缓存读取结果并刷新右侧面板
        try:
            mtime = os.path.getmtime(image_path)
            cached = self.translation_cache.get(image_path, mtime)
            if cached:
                self.origin_text = cached.get("original", "")
                self.translated_text = cached.get("translated", "")
                self._switch_tab("trans")
                # 填充总结区
                summary_dict = cached.get("summary", {})
                if summary_dict and (summary_dict.get("plot") or summary_dict.get("notes")):
                    self._fill_summary(summary_dict)
                else:
                    self.summary_text_edit.setPlainText("本页暂未生成总结")
                self.status_bar.showMessage("预翻译缓存命中，已刷新", 3000)
            else:
                _logger.warning(f"预翻译页面完成但缓存未命中: {image_path}")
        except Exception as e:
            _logger.warning(f"预翻译页面完成刷新 UI 失败: {e}")

    def _on_prefetch_all_completed(self):
        """预翻译全部完成 → 状态栏提示 + 按钮恢复"""
        self.status_bar.showMessage("📦 预翻译完成，已缓存", 3000)
        self.prefetch_btn.setText("预翻译")

    # ===================== 批量翻译 =====================

    def _show_batch_dialog(self):
        """弹出批量翻译范围选择对话框"""
        total = len(self.file_browser.get_file_paths())
        if total == 0:
            self.status_bar.showMessage("请先打开图片文件夹或压缩包", 3000)
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("批量翻译")
        layout = QVBoxLayout(dlg)

        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("范围: 第"))
        start_spin = QSpinBox()
        start_spin.setRange(1, total)
        start_spin.setValue(1)
        range_layout.addWidget(start_spin)
        range_layout.addWidget(QLabel("页 ~ 第"))
        end_spin = QSpinBox()
        end_spin.setRange(1, total)
        end_spin.setValue(total)
        range_layout.addWidget(end_spin)
        range_layout.addWidget(QLabel("页"))
        layout.addLayout(range_layout)

        count_label = QLabel(f"共 0 页")
        layout.addWidget(count_label)

        def _on_range_changed():
            s = start_spin.value()
            e = end_spin.value()
            if s <= e:
                count_label.setText(f"共 {e - s + 1} 页")
            else:
                count_label.setText(f"共 0 页（起点大于终点）")
        start_spin.valueChanged.connect(_on_range_changed)
        end_spin.valueChanged.connect(_on_range_changed)
        _on_range_changed()

        context_check = QCheckBox("启用上下文连贯")
        context_check.setChecked(True)
        layout.addWidget(context_check)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("开始翻译")
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        start, end = start_spin.value() - 1, end_spin.value() - 1  # 转 0-based
        enable_context = context_check.isChecked()

        if start > end:
            start, end = end, start

        page_count = end - start + 1
        if page_count > 50:
            QMessageBox.warning(self, "范围过大", "单次最多翻译 50 页")
            return

        # 耗时提示（> 15 页时弹出预估确认）
        if page_count > BATCH_TIME_THRESHOLD:
            if not self._confirm_batch_start(page_count):
                return

        target_paths = self.file_browser.get_file_paths()[start:end+1]

        if enable_context:
            try:
                from engine.context import ContextEngine
                context_engine = ContextEngine(self.translation_cache._db)
                self.batch_manager.set_context_engine(context_engine)
            except (ImportError, AttributeError):
                _logger.warning("ContextEngine 不可用（PDR-03 尚未实现），上下文功能降级")
                self.batch_manager.set_context_engine(None)
        else:
            # 取消勾选时清空，避免沿用上一次批量任务残留的引擎
            self.batch_manager.set_context_engine(None)

        self._show_batch_progress()
        self.batch_manager.start(target_paths, start, end)

    def _confirm_batch_start(self, page_count: int) -> bool:
        """弹出批量翻译耗时确认对话框，返回是否继续"""
        concurrency = 2  # 默认并发数
        estimated_secs = page_count * PAGE_AVG_TIME_SEC / concurrency

        min_min = max(1, int(estimated_secs / 60 * 0.7))
        max_min = max(1, int(estimated_secs / 60 * 1.3) + 1)

        if max_min <= 1:
            time_str = "不到 1 分钟"
        else:
            time_str = f"{min_min}–{max_min} 分钟"

        msg = (f"将翻译 {page_count} 页\n\n"
               f"预计约 {time_str}，请耐心等待\n\n"
               f"提示：可先翻译少量页面，确认翻译质量满意后再继续。")

        reply = QMessageBox.question(
            self, "批量翻译确认", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        return reply == QMessageBox.StandardButton.Yes

    def _show_batch_progress(self):
        """显示批量翻译进度 UI"""
        self.batch_progress_bar.setValue(0)
        self.batch_progress_bar.setMaximum(100)
        self.batch_progress_label.setText("准备中…")
        self.batch_progress_frame.show()

    def _on_batch_progress(self, completed, total):
        """批量翻译进度更新回调"""
        if total > 0:
            pct = int(completed / total * 100)
            self.batch_progress_bar.setValue(pct)
        self.batch_progress_label.setText(f"{completed} / {total} 页已完成")

    def _on_batch_finished(self, success, failed):
        """批量翻译完成回调"""
        self.batch_progress_frame.hide()
        if failed:
            self.status_bar.showMessage(f"批量翻译完成：{success} 成功，{failed} 失败", 5000)
        else:
            self.status_bar.showMessage(f"批量翻译完成：{success} 页", 5000)

    def _on_batch_pause_resume(self):
        """暂停/恢复切换"""
        if self.batch_manager.is_paused():
            self.batch_manager.resume()
            self.batch_pause_btn.setText("暂停")
        else:
            self.batch_manager.pause()
            self.batch_pause_btn.setText("继续")

    def _on_batch_cancel(self):
        """取消批量翻译"""
        self.batch_manager.cancel()
        self.batch_progress_frame.hide()

    def translate_current_page(self):
        """F5 翻译当前页"""
        if not self.canvas.current_image_path:
            self.status_bar.showMessage("请先打开一张图片", 3000)
            return
        image_path = self.canvas.current_image_path
        self.prefetch_manager.promote(image_path)
        self.translation_controller.translate_page(image_path, page_index=self.current_file_index)
    
    def keyPressEvent(self, event):
        """键盘快捷键：左右方向键翻页、F5 翻译当前页、Ctrl+Shift+F5 预翻译下 3 页"""
        modifiers = event.modifiers()
        if event.key() == Qt.Key.Key_F5 and modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            self._manual_prefetch(3)
        elif event.key() == Qt.Key.Key_F5:
            self.translate_current_page()
        elif event.key() == Qt.Key.Key_Left:
            self._nav_prev_page()
        elif event.key() == Qt.Key.Key_Right:
            self._nav_next_page()
        else:
            super().keyPressEvent(event)
    
    def closeEvent(self, event):
        """窗口关闭时优雅停止所有后台线程并清理临时目录和文件"""
        # 文件浏览器关闭清理（保存阅读位置 + 清理压缩包临时目录）
        self.file_browser.shutdown()
        # 终止预翻译 worker
        self.prefetch_manager.clear()
        # 终止批量翻译 worker
        self.batch_manager.cancel()
        # 终止翻译 worker + 清理临时文件
        self.translation_controller.shutdown()
        # 终止图片缓存管理器中的后台 worker
        self.image_cache.clear()
        # 关闭翻译缓存（WAL checkpoint + close，确保数据不丢失）
        self.translation_cache.close()
        event.accept()
