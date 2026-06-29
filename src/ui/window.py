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
    QDialogButtonBox   # 按钮盒（确定/取消按钮组）
)

from PyQt6.QtGui import (
    QAction,           # 动作（可绑定到工具栏按钮）
    QIcon,             # 图标
    QPixmap            # 图片对象，用于显示图像
)

from PyQt6.QtCore import (
    Qt,                # 常量定义（如对齐方式）
    QThread,           # 线程基类
    pyqtSignal         # 信号定义（线程间通信）
)

# ============================================================================
# 标准库导入
# ============================================================================
import os               # 文件路径操作
import tempfile         # 临时文件目录
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
# - finished: 任务完成时发射，携带原文和译文（str, str）
# - error:    发生错误时发射，携带错误信息
# - status:   状态更新时发射，用于显示当前进度
# ============================================================================
class TranslationWorker(QThread):
    # 定义信号，pyqtSignal用于跨线程通信
    # (str, str) 表示信号携带两个字符串参数
    finished = pyqtSignal(str, str)  # origin_text, translated_text
    error = pyqtSignal(str)          # 错误信息
    status = pyqtSignal(str)         # 状态信息
    
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
        """
        try:
            self.status.emit("翻译中…")
            origin_text, translated_text = llm_engine.translate_image(self.image_path)
            self.finished.emit(origin_text, translated_text)
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
        
        # === 图片缓存与异步加载 ===
        # LRU缓存：最多缓存10张已解码的 QPixmap，翻回同一页秒开
        self.pixmap_cache = OrderedDict()   # path -> QPixmap
        self.pending_loads = {}             # path -> ImageLoadWorker（防止重复加载）
        self.current_file_index = -1        # 当前显示的文件在列表中的索引
        self.MAX_CACHE_SIZE = 10            # 最大缓存页数
        self.PREFETCH_RANGE = 2             # 相邻预加载范围（前后各2页）
        
        # 初始化UI
        self.init_ui()
    
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
        
        # "设置"按钮
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.open_settings)
        toolbar.addAction(settings_action)
        
        # ===== 主布局 =====
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)  # 水平布局
        
        # 使用分割器，可以拖动调整各区域大小
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # --- 1. 文件列表（左侧，固定宽度200px）---
        self.file_list = QListWidget()
        self.file_list.setFixedWidth(200)
        self.file_list.itemClicked.connect(self.load_image)  # 点击文件时加载图片
        splitter.addWidget(self.file_list)
        
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
        
        # --- 工具栏行 ---
        tool_row = QHBoxLayout()
        self.translate_page_btn = QPushButton("翻译当前页")
        self.translate_page_btn.clicked.connect(self.translate_current_page)
        tool_row.addWidget(self.translate_page_btn)
        tool_row.addStretch()
        # 语言标签（从 llm_engine.target_lang 读取）
        self.lang_label = QLabel(f"语言: {llm_engine.target_lang}")
        tool_row.addWidget(self.lang_label)
        right_layout.addLayout(tool_row)
        
        # --- 原文区域 ---
        right_layout.addWidget(QLabel("▼ 原文"))
        self.origin_text_edit = QTextEdit()
        self.origin_text_edit.setReadOnly(True)
        self.origin_text_edit.setPlaceholderText("原文将显示在此…")
        right_layout.addWidget(self.origin_text_edit)
        
        # --- 译文区域 ---
        self.trans_label = QLabel(f"▼ 译文（{llm_engine.target_lang}）")
        right_layout.addWidget(self.trans_label)
        self.trans_text_edit = QTextEdit()
        self.trans_text_edit.setReadOnly(True)
        self.trans_text_edit.setPlaceholderText("译文将显示在此…")
        right_layout.addWidget(self.trans_text_edit)
        
        splitter.addWidget(right_panel)
        
        # 设置分割器初始比例：[200, 600, 300]
        splitter.setSizes([200, 600, 300])
        
        # ===== 状态栏 =====
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("BubbleTrans v2.0 - 就绪")
    
    # ===================== 槽函数 =====================
    
    def open_folder(self):
        """
        打开文件夹对话框
        
        弹出文件夹选择对话框，选择后加载文件夹中的图片文件
        """
        _logger.info("open_folder: 弹出目录选择对话框")
        folder = QFileDialog.getExistingDirectory(self, "Select Comic Folder")
        if folder:
            t0 = time.time()
            _logger.info(f"open_folder: 已选择目录 {folder}")
            self.current_folder = folder
            self._clear_image_cache()   # 切换文件夹时清空旧缓存
            _logger.info(f"open_folder: _clear_image_cache 耗时 {time.time()-t0:.3f}s")
            t1 = time.time()
            self.load_file_list()
            _logger.info(f"open_folder: load_file_list 耗时 {time.time()-t1:.3f}s")
            self.status_bar.showMessage(f"Loaded folder: {folder}")
    
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
        """执行翻页：修改文件列表选中项并触发图片加载"""
        count = self.file_list.count()
        if count == 0:
            return
        current = self.file_list.currentRow()
        new_row = current + delta
        if 0 <= new_row < count:
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
        # 临时更新面板标签
        self.origin_text_edit.setPlaceholderText("▼ 框选原文")
        self.trans_text_edit.setPlaceholderText("▼ 框选译文")
        self.origin_text_edit.clear()
        self.trans_text_edit.clear()
        
        # 保存临时文件（使用唯一文件名，避免并发冲突）
        try:
            temp_dir = tempfile.gettempdir()
            # 用 uuid 生成唯一文件名，避免多次框选时的并发覆盖问题
            unique_name = f"bubbletrans_{uuid.uuid4().hex[:8]}.png"
            temp_path = os.path.join(temp_dir, unique_name)
            pixmap.save(temp_path, "PNG")
            self._temp_files.append(temp_path)  # 记录待清理的临时文件
            
            # 启动翻译工作线程
            self.worker = TranslationWorker(temp_path)
            # 连接信号（线程完成时更新UI）
            self.worker.status.connect(self.status_bar.showMessage)
            self.worker.finished.connect(self.on_translation_finished)
            self.worker.error.connect(self.on_translation_error)
            self.worker.start()  # 启动线程
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"保存临时图片失败: {e}")
    
    def on_translation_finished(self, origin_text, translated_text):
        """
        翻译完成回调函数 - v2.0：直接显示原文段落和译文段落
        
        当TranslationWorker完成翻译后，此方法被调用
        
        参数:
            origin_text:     原文文本
            translated_text: 译文文本
        """
        self.origin_text_edit.setText(origin_text)
        self.trans_text_edit.setText(translated_text)
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
        """设置翻译进行中状态，防止重复点击"""
        self.translate_page_btn.setEnabled(not active)
        if active:
            self.translate_page_btn.setText("翻译中…")
        else:
            self.translate_page_btn.setText("翻译当前页")
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
        self._set_translating(True)
        self.status_bar.showMessage("翻译中…")
        self.origin_text_edit.clear()
        self.trans_text_edit.clear()
        self.origin_text_edit.setText("翻译中…")
        
        self.worker = TranslationWorker(image_path)
        self.worker.status.connect(self.status_bar.showMessage)
        self.worker.finished.connect(self.on_translation_finished)
        self.worker.error.connect(self.on_translation_error)
        self.worker.start()
    
    def keyPressEvent(self, event):
        """键盘快捷键：左右方向键翻页（画布未聚焦时也可用）"""
        if event.key() == Qt.Key.Key_Left:
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
    
    def closeEvent(self, event):
        """窗口关闭时优雅停止所有后台线程并清理临时文件"""
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
        # 清理临时文件
        self._clean_temp_files()
        event.accept()
