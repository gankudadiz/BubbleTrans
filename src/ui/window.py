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
- TranslationWorker: 后台线程，负责LLM翻译任务
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
    QStatusBar,        # 状态栏
    QMessageBox,       # 消息对话框
    QApplication,      # 应用程序对象（用于获取屏幕信息）
    QDialog,           # 对话框基类
    QDialogButtonBox,  # 按钮盒（确定/取消按钮组）
    QFrame,            # 框架容器（骨架屏占位块）
    QCheckBox,         # 复选框
    QLineEdit,         # 单行文本输入框（搜索框）
    QShortcut,         # 快捷键绑定（Ctrl+F / Esc）
)

from PyQt6.QtGui import (
    QAction,           # 动作（可绑定到工具栏按钮）
    QIcon,             # 图标
    QPixmap,           # 图片对象，用于显示图像
    QKeySequence,      # 快捷键序列（QShortcut 绑定用）
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
import tempfile         # 临时文件目录
import zipfile          # ZIP 格式校验
import uuid             # 唯一标识，用于生成不重复的临时文件名
import time             # 耗时统计
import logging          # 日志记录
from collections import OrderedDict  # LRU缓存

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
from utils.config import load_config, save_config


# ============================================================================
# TranslationWorker 类 - 翻译工作线程
# ============================================================================
# 继承自QThread，用于在后台执行耗时的LLM翻译任务
# 
# 为什么需要线程？
# - LLM翻译是耗时操作，可能需要几秒钟
# - 如果在主线程执行，会导致GUI界面卡死
# - 使用QThread可以在后台执行这些任务，不阻塞UI响应
#
# 信号说明：
# - finished: 任务完成时发射，携带原文、译文和总结字典（str, str, dict）
# - error:    发生错误时发射，携带错误信息
# - status:   状态更新时发射，用于显示当前进度
# ============================================================================
class TranslationWorker(QThread):
    # 定义信号，pyqtSignal用于跨线程通信
    finished = pyqtSignal(str, str, dict)  # origin_text, translated_text, summary_dict
    error = pyqtSignal(str)                # 错误信息
    status = pyqtSignal(str)               # 状态信息（已弃用，保留兼容）
    stage_changed = pyqtSignal(str)        # 阶段变化（编码/等待/解析/完成）
    
    def __init__(self, image_path):
        """
        初始化翻译工作线程
        
        参数:
            image_path: 要翻译的图片路径
        """
        super().__init__()
        self.image_path = image_path
    
    def run(self):
        """
        线程主函数 - 直接使用LLM翻译图片
        
        使用LLM的视觉能力直接识别并翻译图片中的文字
        分阶段发射进度信号供 UI 层更新状态栏
        """
        try:
            self.stage_changed.emit("正在翻译…")
            origin_text, translated_text, summary_dict = llm_engine.translate_image(self.image_path)
            self.stage_changed.emit("正在解析…")
            self.finished.emit(origin_text, translated_text, summary_dict)
        except Exception as e:
            self.error.emit(str(e))


# ============================================================================
# ImageLoadWorker 类 - 图片异步解码线程
# ============================================================================
# 继承自QThread，在后台线程中解码QPixmap，避免主线程卡顿
#
# 为什么需要异步解码？
# - 漫画扫描页通常 4000×6000 像素，QPixmap 解码需 200-800ms
# - 在主线程解码会导致整个窗口冻结
# - 后台解码 + 占位文字 = 流畅体验
#
# 信号说明：
# - loaded: 解码完成时发射 (image_path, QPixmap)
# - error:  解码失败时发射 (image_path, error_msg)
# ============================================================================
class ImageLoadWorker(QThread):
    """后台线程：异步解码图片文件为 QPixmap"""
    loaded = pyqtSignal(str, QPixmap)  # image_path, pixmap
    error = pyqtSignal(str, str)       # image_path, error_msg
    
    def __init__(self, image_path):
        super().__init__()
        self.image_path = image_path
    
    def run(self):
        """在后台线程中执行 QPixmap 解码"""
        try:
            pixmap = QPixmap(self.image_path)
            if pixmap.isNull():
                self.error.emit(self.image_path, f"无法解码: {self.image_path}")
            else:
                self.loaded.emit(self.image_path, pixmap)
        except Exception as e:
            self.error.emit(self.image_path, str(e))


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
        self.current_folder = ""      # 当前打开的文件夹路径
        self.worker = None            # 翻译工作线程实例
        self._temp_files = []         # 待清理的临时文件路径列表
        self._archive_temp_dir = ""   # 压缩包解压的临时目录（非空表示当前来源是压缩包）
        
        # 右侧面板状态
        self.origin_text = ""         # 当前原文
        self.translated_text = ""     # 当前译文
        self.current_tab = "trans"    # 当前选中的 tab（默认译文）
        self._translating_image_path = ""  # 正在翻译的图片路径（用于缓存判断）
        
        # === 图片缓存与异步加载 ===
        # LRU缓存：最多缓存10张已解码的 QPixmap，翻回同一页秒开
        self.pixmap_cache = OrderedDict()   # path -> QPixmap
        self.pending_loads = {}             # path -> ImageLoadWorker（防止重复加载）
        self.current_file_index = -1        # 当前显示的文件在列表中的索引
        self.MAX_CACHE_SIZE = 10            # 最大缓存页数
        self.PREFETCH_RANGE = 2             # 相邻预加载范围（前后各2页）
        
        # 初始化翻译缓存（注入到全局 llm_engine 实例）
        self.translation_cache = TranslationCache()
        llm_engine.cache = self.translation_cache

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
        
        # "打开文件夹"按钮
        open_action = QAction("Open Folder", self)
        open_action.triggered.connect(self.open_folder)  # 点击时调用open_folder方法
        toolbar.addAction(open_action)

        # "打开压缩包"按钮（新增：支持 .cbz / .zip 漫画压缩包）
        open_archive_action = QAction("Open Archive", self)
        open_archive_action.triggered.connect(self.open_archive)
        toolbar.addAction(open_archive_action)

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
        main_layout = QHBoxLayout(central_widget)  # 水平布局
        
        # 使用分割器，可以拖动调整各区域大小
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # --- 1. 左侧面板（搜索框 + 文件列表，固定宽度200px）---
        # 容器 widget：包裹搜索框和文件列表，作为整体加入 QSplitter
        left_panel = QWidget()
        left_panel.setFixedWidth(200)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        # 搜索框（顶部）
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 搜索文件名…")
        self.search_box.setClearButtonEnabled(True)  # 右侧 X 按钮一键清空
        self.search_box.textChanged.connect(self.filter_file_list)  # 实时过滤
        left_layout.addWidget(self.search_box)

        # 文件列表（下部，占据剩余空间）
        self.file_list = QListWidget()
        self.file_list.itemClicked.connect(self.load_image)  # 点击文件时加载图片
        left_layout.addWidget(self.file_list)

        splitter.addWidget(left_panel)

        # 快捷键绑定
        # Ctrl+F：聚焦搜索框（context=self，主窗口任意位置可用）
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search_box)
        # Esc：清空搜索框（context=self.search_box，仅搜索框有焦点时触发）
        # Qt 在 shortcut 层拦截 Esc，不经过 keyPressEvent，避免与画布/主窗口冲突
        QShortcut(QKeySequence("Escape"), self.search_box, self._clear_search)
        
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
        
        # --- 按钮行 ---
        tool_row = QHBoxLayout()
        self.translate_page_btn = QPushButton("翻译当前页")
        self.translate_page_btn.clicked.connect(self.translate_current_page)
        tool_row.addWidget(self.translate_page_btn)
        # 清除缓存按钮（小字，非主要操作）
        self.clear_cache_btn = QPushButton("清除缓存")
        self.clear_cache_btn.setStyleSheet("QPushButton { color: #888; font-size: 11px; padding: 2px 8px; }")
        self.clear_cache_btn.clicked.connect(self._clear_translation_cache)
        tool_row.addWidget(self.clear_cache_btn)
        tool_row.addStretch()
        # 语言标签（从 llm_engine.target_lang 读取）
        self.lang_label = QLabel(f"语言: {llm_engine.target_lang}")
        tool_row.addWidget(self.lang_label)
        right_layout.addLayout(tool_row)
        
        # --- 分段切换按钮："原文" / "译文" ---
        seg_container = QWidget()
        seg_container.setObjectName("segContainer")
        seg_container.setStyleSheet("""
            QWidget#segContainer {
                background-color: #1e1e1e;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 2px;
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
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 13px;
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

    def _clear_translation_cache(self):
        """清除全部翻译缓存（带确认对话框）"""
        count = len(self.translation_cache)
        if count == 0:
            self.status_bar.showMessage("缓存为空，无需清除", 3000)
            return
        reply = QMessageBox.question(
            self, "清除翻译缓存",
            f"当前共有 {count} 条翻译缓存。\n清除后需要重新翻译所有页面。\n\n确定清除吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.translation_cache.clear()
            self.status_bar.showMessage(f"已清除 {count} 条翻译缓存", 5000)

    # ===================== 槽函数 =====================
    
    def open_folder(self):
        """
        打开文件夹对话框

        弹出文件夹选择对话框，选择后加载文件夹中的图片文件
        """
        _logger.info("open_folder: 弹出目录选择对话框")
        folder = QFileDialog.getExistingDirectory(self, "Select Comic Folder")
        if folder:
            self._load_source(folder, is_archive=False)

    def open_archive(self):
        """
        打开漫画压缩包对话框

        弹出文件选择对话框，选择 .cbz/.zip 压缩包后解压到临时目录并加载
        """
        _logger.info("open_archive: 弹出压缩包选择对话框")
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Comic Archive",
            "",
            "Comic Archive (*.cbz *.zip)"
        )
        if file_path:
            self._load_source(file_path, is_archive=True)

    def _load_source(self, path: str, is_archive: bool):
        """
        统一加载入口：文件夹或压缩包分发

        参数:
            path: 文件夹路径或压缩包文件路径
            is_archive: True 表示压缩包，False 表示文件夹
        """
        # 清理上一次的压缩包临时目录（如有）
        self._cleanup_archive_temp()

        if is_archive:
            archive_name = os.path.basename(path)
            _logger.info(f"_load_source: 解压压缩包 {archive_name}")
            try:
                temp_dir, image_files = archive.extract_to_temp(path)
                self._archive_temp_dir = temp_dir
                self.current_folder = temp_dir
            except (ValueError, zipfile.BadZipFile, OSError) as e:
                _logger.error(f"_load_source: 解压失败 {archive_name}: {e}")
                QMessageBox.critical(self, "解压失败", str(e))
                return
            except Exception as e:
                # 兜底：捕获 CRC 校验失败(binascii.Error)等未预料的异常
                _logger.error(f"_load_source: 解压遇到未知错误 {archive_name}: {e}")
                QMessageBox.critical(self, "解压失败", f"无法打开压缩包: {e}")
                return
            _logger.info(f"_load_source: 解压完成 {archive_name}，共 {len(image_files)} 张图片")
        else:
            _logger.info(f"_load_source: 打开目录 {path}")
            self.current_folder = path

        # 清空旧缓存并加载文件列表
        t0 = time.time()
        self._clear_image_cache()
        _logger.info(f"_load_source: _clear_image_cache 耗时 {time.time()-t0:.3f}s")
        t1 = time.time()
        self.load_file_list()
        _logger.info(f"_load_source: load_file_list 耗时 {time.time()-t1:.3f}s")

        # 状态栏文案
        total = self.file_list.count()
        if is_archive:
            self.status_bar.showMessage(f"📦 {os.path.basename(path)} ({total} 页)")
        else:
            self.status_bar.showMessage(f"已加载: {os.path.basename(path)} ({total} 张)")
    
    def load_file_list(self):
        """
        加载文件列表

        从当前文件夹中读取图片文件，并显示在左侧列表中
        支持的图片格式：jpg, jpeg, png, webp, bmp
        """
        self.file_list.clear()
        valid_exts = ['.jpg', '.jpeg', '.png', '.webp', '.bmp']

        try:
            # 获取文件夹中所有符合条件的文件
            t0 = time.time()
            files = sorted([
                f for f in os.listdir(self.current_folder)
                if os.path.splitext(f)[1].lower() in valid_exts
            ])
            _logger.info(f"load_file_list: os.listdir + sorted 扫描 {len(files)} 个文件，耗时 {time.time()-t0:.3f}s")
            # 添加到列表控件
            t1 = time.time()
            self.file_list.addItems(files)
            _logger.info(f"load_file_list: addItems 耗时 {time.time()-t1:.3f}s")
        except Exception as e:
            _logger.error(f"load_file_list 失败: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load folder: {e}")

    # ===================== 文件搜索 =====================

    def filter_file_list(self, query: str):
        """
        根据搜索框输入实时过滤文件列表

        遍历所有 item，将不匹配的项 setHidden(True)。
        空 query 时恢复全部显示。

        参数:
            query: 搜索框中的文本（已自动触发 textChanged 信号）
        """
        query = query.strip().lower()
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if not query:
                item.setHidden(False)
            else:
                item.setHidden(query not in item.text().lower())

    def _focus_search_box(self):
        """Ctrl+F 快捷键槽：聚焦搜索框并全选当前文本"""
        self.search_box.setFocus()
        self.search_box.selectAll()

    def _clear_search(self):
        """
        Esc 快捷键槽（仅搜索框有焦点时触发）：清空搜索框并失去焦点

        焦点回到文件列表，方便用户继续用方向键浏览。
        """
        self.search_box.clear()
        self.file_list.setFocus()
    
    def load_image(self, item):
        """
        加载图片到画布（带 LRU 缓存 + 异步解码 + 预加载）

        当用户点击文件列表中的某个文件时调用

        优化策略：
        1. 命中 LRU 缓存 → 直接显示（秒开）
        2. 未命中 → 显示"加载中…"占位，后台线程异步解码
        3. 解码完成后自动触发相邻页预加载

        参数:
            item: 点击的列表项（QListWidgetItem）
        """
        file_name = item.text()
        file_path = os.path.join(self.current_folder, file_name)
        self.current_file_index = self.file_list.currentRow()
        
        # 立即更新页码和按钮状态（不等图片解码）
        self._update_page_info()
        
        # === 第一步：检查 LRU 缓存 ===
        if file_path in self.pixmap_cache:
            pixmap = self.pixmap_cache[file_path]
            self.pixmap_cache.move_to_end(file_path)  # 更新 LRU 位置（标记最近使用）
            self.status_bar.showMessage(f"选中: {file_name} (缓存命中)")
            self.canvas.load_image(file_path, pixmap=pixmap)
            self._update_page_info()   # 刷新页码（_current_image_path 已正确设置）
            self._set_translating(False)
            self._prefetch_adjacent()  # 仍然预加载相邻页
            return
        
        # === 第二步：未命中缓存，异步加载 ===
        self.canvas.show_placeholder("加载中…")
        self.status_bar.showMessage(f"加载中: {file_name}…")
        self._set_translating(False)
        
        # 启动后台解码线程
        worker = ImageLoadWorker(file_path)
        worker.loaded.connect(self._on_image_loaded)
        worker.error.connect(self._on_image_load_error)
        self.pending_loads[file_path] = worker
        worker.start()
    
    # ===================== 图片缓存与异步加载辅助方法 =====================
    
    def _on_image_loaded(self, image_path, pixmap):
        """异步图片解码完成回调 —— 加入缓存并渲染到画布"""
        self._add_to_cache(image_path, pixmap)
        self.pending_loads.pop(image_path, None)
        
        # 仅当用户没有在此间切到其他页时才渲染
        current_item = self.file_list.currentItem()
        if current_item:
            current_path = os.path.join(self.current_folder, current_item.text())
            if image_path == current_path:
                self.canvas.load_image(image_path, pixmap=pixmap)
                self.status_bar.showMessage(f"已加载: {os.path.basename(image_path)}")
                self._update_page_info()   # 刷新页码指示器
                self._prefetch_adjacent()
    
    def _on_image_load_error(self, image_path, error_msg):
        """异步图片解码失败回调"""
        self.pending_loads.pop(image_path, None)
        current_item = self.file_list.currentItem()
        if current_item:
            current_path = os.path.join(self.current_folder, current_item.text())
            if image_path == current_path:
                self.canvas.show_placeholder(f"加载失败: {error_msg}")
                self.status_bar.showMessage(f"错误: {error_msg}")
    
    def _add_to_cache(self, path, pixmap):
        """向 LRU 缓存添加一条记录，超过上限时自动淘汰最旧的"""
        if path in self.pixmap_cache:
            self.pixmap_cache.move_to_end(path)
        self.pixmap_cache[path] = pixmap
        if len(self.pixmap_cache) > self.MAX_CACHE_SIZE:
            # popitem(last=False) 弹出最旧的（最先插入的）
            self.pixmap_cache.popitem(last=False)
    
    def _prefetch_adjacent(self):
        """预加载当前页前后的相邻页面到缓存"""
        if self.current_file_index < 0:
            return
        total = self.file_list.count()
        for offset in range(1, self.PREFETCH_RANGE + 1):
            for idx in (self.current_file_index + offset, self.current_file_index - offset):
                if 0 <= idx < total:
                    file_path = os.path.join(self.current_folder,
                                             self.file_list.item(idx).text())
                    # 跳过已缓存或正在加载的
                    if file_path in self.pixmap_cache or file_path in self.pending_loads:
                        continue
                    worker = ImageLoadWorker(file_path)
                    worker.loaded.connect(self._on_prefetch_loaded)
                    # 预加载错误静默忽略
                    worker.error.connect(lambda p, e: self.pending_loads.pop(p, None))
                    self.pending_loads[file_path] = worker
                    worker.start()
    
    def _on_prefetch_loaded(self, image_path, pixmap):
        """预加载完成回调 —— 静默加入缓存，不渲染到画布"""
        self._add_to_cache(image_path, pixmap)
        self.pending_loads.pop(image_path, None)
    
    def _clear_image_cache(self):
        """清空所有图片缓存和进行中的加载（切换文件夹时调用）"""
        self.pixmap_cache.clear()
        # 终止所有进行中的后台解码线程
        for path, worker in list(self.pending_loads.items()):
            if worker.isRunning():
                worker.terminate()
                worker.wait(500)        # 等待线程结束（最多0.5秒，避免阻塞UI）
                worker.deleteLater()    # 安全释放 Qt 资源
        self.pending_loads.clear()
        self.current_file_index = -1
        # 隐藏导航按钮和页码指示器
        self.canvas._hide_nav_overlay()
    
    # ===================== 页面导航 =====================
    
    def _nav_prev_page(self):
        """← 前翻页（由画布箭头按钮或键盘左方向键触发）"""
        self._navigate_page(-1)
    
    def _nav_next_page(self):
        """→ 后翻页（由画布箭头按钮或键盘右方向键触发）"""
        self._navigate_page(1)
    
    def _navigate_page(self, delta: int):
        """
        执行翻页：修改文件列表选中项并触发图片加载

        过滤状态下自动跳过隐藏项，跳到下一个可见项；
        如果方向上没有可见项（到达边界），则不翻页。
        """
        count = self.file_list.count()
        if count == 0:
            return
        current = self.file_list.currentRow()
        new_row = current
        while True:
            new_row += delta
            if new_row < 0 or new_row >= count:
                return  # 边界外，不翻页
            if not self.file_list.item(new_row).isHidden():
                break
        self.file_list.setCurrentRow(new_row)
        item = self.file_list.item(new_row)
        self.load_image(item)
    
    def _update_page_info(self):
        """刷新画布上的页码指示器和按钮可用状态"""
        count = self.file_list.count()
        if count == 0:
            return
        current = self.file_list.currentRow()
        if current >= 0:
            self.canvas.update_page_indicator(current + 1, count)
        # 首页禁用前翻，末页禁用后翻（仅当按钮已初始化时）
        if self.canvas._btn_prev is not None:
            self.canvas._btn_prev.setEnabled(current > 0)
            self.canvas._btn_next.setEnabled(current < count - 1)
    
    # ===================== 设置对话框 =====================
    
    def open_settings(self):
        """
        打开设置对话框
        
        弹出设置对话框，让用户配置OCR和LLM相关设置
        """
        dlg = SettingsDialog(self)
        dlg.exec()  # exec()以模态方式显示对话框
    
    # ===================== 分段切换 =====================
    
    def _switch_tab(self, tab):
        """
        切换原文/译文 tab

        参数:
            tab: "origin" 或 "trans"
        """
        self.current_tab = tab
        self.btn_origin_seg.setChecked(tab == "origin")
        self.btn_trans_seg.setChecked(tab == "trans")
        text = self.origin_text if tab == "origin" else self.translated_text
        self.shared_text_edit.setText(text if text else "")
    
    # ===================== 翻译回调 =====================
    
    def handle_region_selected(self, pixmap: QPixmap):
        """
        处理框选区域完成事件
        
        当用户在画布上完成框选后，此方法被调用
        弹出确认对话框，用户确认后开始翻译
        
        参数:
            pixmap: 框选的图片区域（QPixmap格式）
        """
        self.status_bar.showMessage("已选中区域，等待确认...", 3000)
        
        # 创建确认对话框
        dlg = CropConfirmDialog(pixmap, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            self.status_bar.showMessage("已取消本次选区", 3000)
            return
        
        # 用户确认后，开始处理
        self._set_translating(True)
        self.status_bar.showMessage("翻译中...")
        self.origin_text = ""
        self.translated_text = ""
        self.shared_text_edit.clear()
        
        # 保存临时文件（使用唯一文件名，避免并发冲突）
        try:
            temp_dir = tempfile.gettempdir()
            # 用 uuid 生成唯一文件名，避免多次框选时的并发覆盖问题
            unique_name = f"bubbletrans_{uuid.uuid4().hex[:8]}.png"
            temp_path = os.path.join(temp_dir, unique_name)
            self._translating_image_path = temp_path  # 临时文件路径（缓存时会过滤）
            pixmap.save(temp_path, "PNG")
            self._temp_files.append(temp_path)  # 记录待清理的临时文件
            
            # 启动翻译工作线程
            self.worker = TranslationWorker(temp_path)
            # 连接信号（线程完成时更新UI）
            self.worker.stage_changed.connect(self._on_translation_stage)
            self.worker.finished.connect(self.on_translation_finished)
            self.worker.error.connect(self.on_translation_error)
            self.worker.start()  # 启动线程
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"保存临时图片失败: {e}")
    
    def _on_translation_stage(self, stage: str):
        """翻译阶段变化 → 更新状态栏"""
        self.status_bar.showMessage(stage)

    def on_translation_finished(self, origin_text, translated_text, summary_dict):
        """
        翻译完成回调函数

        当TranslationWorker完成翻译后，此方法被调用

        参数:
            origin_text:     原文文本
            translated_text: 译文文本
            summary_dict:    总结数据字典 {"plot": "剧情摘要", "notes": "翻译备注"}
        """
        self.origin_text = origin_text
        self.translated_text = translated_text

        # 仅缓存完整页面翻译结果（非临时文件的框选翻译）
        if not llm_engine.last_from_cache and self._translating_image_path:
            current_path = self._translating_image_path
            if current_path and os.path.exists(current_path):
                # 框选翻译使用临时文件，不应缓存
                is_temp = tempfile.gettempdir() in current_path
                if not is_temp:
                    mtime = os.path.getmtime(current_path)
                    self.translation_cache.set(current_path, mtime, {
                        "original": origin_text,
                        "translated": translated_text,
                        "summary": summary_dict,
                    })
                    self.translation_cache.save()
            self._translating_image_path = ""

        # 自动切换到译文 tab
        self._switch_tab("trans")
        
        # 填充总结区
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
                # 正则处理换行：LLM 返回的 \n 在 HTML 中被忽略，统一转为 <br>
                # 同时处理 " - " 模式，确保列表项各自独占一行
                notes_html = notes.replace('\n', '<br>')
                notes_html = re.sub(r'\s+-\s+', '<br>- ', notes_html)
                html_parts.append(notes_html)
            self.summary_text_edit.setHtml("".join(html_parts))
        else:
            self.summary_text_edit.setPlainText("本页暂未生成总结")
        
        self._set_translating(False)
        self.status_bar.showMessage("翻译完成", 5000)
    
    def on_translation_error(self, error_msg):
        """
        翻译错误回调函数
        
        当TranslationWorker发生错误时，此方法被调用
        
        参数:
            error_msg: 错误信息
        """
        self.status_bar.showMessage(f"错误: {error_msg}")
        self._set_translating(False)
        QMessageBox.warning(self, "翻译失败", error_msg)
    
    def _set_translating(self, active: bool):
        """设置翻译进行中状态，防止重复点击，并切换骨架屏/按钮动画"""
        self.translate_page_btn.setEnabled(not active)
        if active:
            self._spinner_dots = 0
            self._spinner_timer.start(500)   # 每 0.5s 切换省略号
            self._show_skeleton(True)
            self._start_skeleton_pulse()
        else:
            self._spinner_timer.stop()
            self.translate_page_btn.setText("翻译当前页")
            self._show_skeleton(False)
            self._stop_skeleton_pulse()
            # 如果有进行中的 worker，安全终止它
            if self.worker and self.worker.isRunning():
                self.worker.terminate()
                self.worker.wait(500)        # 等待线程结束（最多0.5秒）
                self.worker.deleteLater()    # 安全释放 Qt 资源
                self.worker = None
            # 清理残留的临时文件
            self._clean_temp_files()
    
    def translate_current_page(self):
        """翻译当前画布中显示的整张图片"""
        if not hasattr(self.canvas, '_current_image_path') or not self.canvas._current_image_path:
            self.status_bar.showMessage("请先打开一张图片", 3000)
            return
        
        image_path = self.canvas._current_image_path
        self._translating_image_path = image_path  # 记录路径用于缓存写回
        self._set_translating(True)
        self.origin_text = ""
        self.translated_text = ""
        self.shared_text_edit.clear()
        
        self.worker = TranslationWorker(image_path)
        self.worker.stage_changed.connect(self._on_translation_stage)
        self.worker.finished.connect(self.on_translation_finished)
        self.worker.error.connect(self.on_translation_error)
        self.worker.start()
    
    def keyPressEvent(self, event):
        """键盘快捷键：左右方向键翻页、F5 翻译当前页（画布未聚焦时也可用）"""
        if event.key() == Qt.Key.Key_F5:
            self.translate_current_page()
        elif event.key() == Qt.Key.Key_Left:
            self._nav_prev_page()
        elif event.key() == Qt.Key.Key_Right:
            self._nav_next_page()
        else:
            super().keyPressEvent(event)
    
    # ===================== 资源清理 =====================
    
    def _clean_temp_files(self):
        """清理所有记录的临时文件"""
        for f in self._temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except OSError:
                pass  # 文件被占用或已删除，忽略
        self._temp_files.clear()
    
    def _cleanup_archive_temp(self):
        """
        清理压缩包临时解压目录

        在切换来源（打开新的文件夹/压缩包）和关闭程序时调用
        """
        if self._archive_temp_dir and os.path.exists(self._archive_temp_dir):
            _logger.info(f"_cleanup_archive_temp: 清理临时目录 {self._archive_temp_dir}")
            try:
                shutil.rmtree(self._archive_temp_dir, ignore_errors=True)
            except Exception as e:
                _logger.warning(f"_cleanup_archive_temp: 清理失败 {e}")
            self._archive_temp_dir = ""

    def closeEvent(self, event):
        """窗口关闭时优雅停止所有后台线程并清理临时目录和文件"""
        # 终止翻译 worker
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait(3000)
            self.worker.deleteLater()
            self.worker = None
        # 终止所有图片加载 worker
        for path, worker in list(self.pending_loads.items()):
            if worker.isRunning():
                worker.terminate()
                worker.wait(3000)
                worker.deleteLater()
        self.pending_loads.clear()
        # 清理临时文件（框选翻译产生的临时图片）
        self._clean_temp_files()
        # 清理压缩包临时解压目录
        self._cleanup_archive_temp()
        # QA：清理完成，标记关闭事件已接受
        event.accept()
