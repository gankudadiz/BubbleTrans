#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - Scrappy Comic Translator 主窗口模块

本模块实现了漫画翻译器的主窗口界面，包含以下功能：
1. 文件浏览 - 左侧面板显示漫画文件夹中的图片文件
2. 图片画布 - 中间面板显示图片，支持框选翻译区域
3. 翻译面板 - 右侧面板显示OCR识别结果和翻译结果
4. 工具栏 - 包含打开文件夹、设置、OCR预热等功能

核心组件：
- MainWindow: 主窗口类，管理整个应用程序的UI
- TranslationWorker: 后台线程，处理OCR识别和翻译任务
- OcrInitWorker: 后台线程，负责OCR引擎初始化
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
    pyqtSignal,        # 信号定义（线程间通信）
    QTimer             # 定时器
)

# ============================================================================
# 标准库导入
# ============================================================================
import os               # 文件路径操作
import tempfile         # 临时文件目录

# ============================================================================
# 项目内部模块导入
# ============================================================================
# 这些模块位于项目的ui和engine目录中
# canvas.py:   图片画布组件，负责显示图片和处理框选
# settings.py: 设置对话框
# ocr.py:      OCR识别引擎
# llm.py:      大语言模型翻译引擎
# ============================================================================
from ui.canvas import ImageCanvas
from ui.settings import SettingsDialog
from engine.ocr import ocr_engine
from engine.llm import llm_engine


# ============================================================================
# TranslationWorker 类 - 翻译工作线程
# ============================================================================
# 继承自QThread，用于在后台执行耗时的OCR识别和翻译任务
# 
# 为什么需要线程？
# - OCR识别和LLM翻译都是耗时操作，可能需要几秒钟
# - 如果在主线程执行，会导致GUI界面卡死
# - 使用QThread可以在后台执行这些任务，不阻塞UI响应
#
# 信号说明：
# - finished: 任务完成时发射，携带OCR结果和翻译结果
# - error:    发生错误时发射，携带错误信息
# - status:   状态更新时发射，用于显示当前进度
# ============================================================================
class TranslationWorker(QThread):
    # 定义信号，pyqtSignal用于跨线程通信
    # (str, str) 表示信号携带两个字符串参数
    finished = pyqtSignal(str, str)  # ocr_text, trans_text
    error = pyqtSignal(str)          # 错误信息
    status = pyqtSignal(str)         # 状态信息
    
    def __init__(self, image_path, context=""):
        """
        初始化翻译工作线程
        
        参数:
            image_path: 要翻译的图片路径
            context:    上下文信息，用于LLM翻译时提供更多背景
        """
        super().__init__()  # 调用父类QThread的构造函数
        self.image_path = image_path
        self.context = context
    
    def run(self):
        """
        线程主函数 - 执行OCR识别和翻译
        
        这个方法在线程启动时自动被调用
        执行流程：
        1. 判断是否使用Vision模式（如果使用则跳过本地OCR）
        2. 执行OCR文字识别
        3. 如果识别到文字，调用LLM进行翻译
        4. 发射信号通知主线程结果
        """
        try:
            # 检查LLM引擎是否支持Vision模式
            # getattr用于安全获取属性，如果属性不存在返回默认值
            use_vision = getattr(llm_engine, 'use_vision', False)
            
            if use_vision:
                # Vision模式：使用LLM直接识别图片中的文字并进行翻译
                # 不需要本地OCR引擎参与
                self.status.emit("Vision 模式：跳过本地 OCR，直接翻译...")
                ocr_text = "Vision 模式：已跳过本地 OCR"
                trans_text = llm_engine.translate("", self.context, self.image_path, True)
                self.finished.emit(ocr_text, trans_text)
                return
            
            # 普通模式：先执行OCR，再进行翻译
            self.status.emit("Running OCR...")
            ocr_text = ocr_engine.recognize(self.image_path)
            
            # 检查OCR是否出错
            if ocr_text.startswith("OCR Error:"):
                self.error.emit(ocr_text)
                return
            
            # 检查是否识别到文字
            if not ocr_text.strip():
                self.error.emit("__OCR_NO_TEXT__")
                return
            
            # 调用LLM进行翻译
            self.status.emit("Translating with LLM...")
            trans_text = llm_engine.translate(ocr_text, self.context, self.image_path, False)
            
            # 发送完成信号，携带OCR结果和翻译结果
            self.finished.emit(ocr_text, trans_text)
            
        except Exception as e:
            # 捕获任何异常并发送错误信号
            self.error.emit(str(e))


# ============================================================================
# OcrInitWorker 类 - OCR初始化工作线程
# ============================================================================
# 专门用于在后台初始化OCR引擎
# 因为OCR引擎（如EasyOCR）初始化可能需要较长时间（加载模型）
# ============================================================================
class OcrInitWorker(QThread):
    finished = pyqtSignal(bool, str)
    
    def run(self):
        """
        执行OCR引擎初始化
        
        完成后发射finished信号：
        - 第一个参数：是否初始化成功（bool）
        - 第二个参数：错误信息（如果失败）
        """
        try:
            ok = ocr_engine.initialize()
            self.finished.emit(bool(ok), "")
        except Exception as e:
            self.finished.emit(False, str(e))


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
        layout.addWidget(QLabel("确认使用该选区进行 OCR/翻译吗？"))
        
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
# 工具栏：包含打开文件夹、设置、OCR预热按钮
# 状态栏：显示当前状态信息
# ============================================================================
class MainWindow(QMainWindow):
    """
    主窗口类 - BubbleTrans漫画翻译器的主界面
    
    功能：
    - 左侧面板：显示漫画文件夹中的图片文件列表
    - 中间面板：显示当前选中的图片，支持框选翻译区域
    - 右侧面板：显示OCR识别结果和翻译结果
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
        self.current_context = ""     # 上下文信息
        self.worker = None            # 翻译工作线程实例
        self.ocr_init_worker = None   # OCR初始化工作线程实例
        self.ocr_init_action = None   # OCR预热按钮（用于禁用/启用）
        
        # 初始化UI
        self.init_ui()
        
        # 如果不使用Vision模式，预热OCR引擎
        if not getattr(llm_engine, "use_vision", False):
            QTimer.singleShot(0, self.warmup_ocr)
    
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
        
        # "OCR预热"按钮
        self.ocr_init_action = QAction("预热 OCR", self)
        self.ocr_init_action.triggered.connect(self.warmup_ocr)
        toolbar.addAction(self.ocr_init_action)
        
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
        splitter.addWidget(self.canvas)
        
        # --- 3. 翻译面板（右侧，固定宽度400px）---
        right_panel = QWidget()
        right_panel.setFixedWidth(300)
        right_layout = QVBoxLayout(right_panel)
        
        # OCR识别结果标签和编辑框
        right_layout.addWidget(QLabel("OCR Text (Editable):"))
        self.ocr_text_edit = QTextEdit()
        self.ocr_text_edit.setPlaceholderText("OCR results will appear here...")
        right_layout.addWidget(self.ocr_text_edit)
        
        # 翻译结果标签和编辑框
        right_layout.addWidget(QLabel("Translation:"))
        self.trans_text_edit = QTextEdit()
        self.trans_text_edit.setPlaceholderText("Translation will appear here...")
        right_layout.addWidget(self.trans_text_edit)
        
        splitter.addWidget(right_panel)
        
        # 设置分割器初始比例：[200, 600, 400]
        splitter.setSizes([200, 600, 400])
        
        # ===== 状态栏 =====
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
    
    # ===================== 槽函数 =====================
    
    def open_folder(self):
        """
        打开文件夹对话框
        
        弹出文件夹选择对话框，选择后加载文件夹中的图片文件
        """
        folder = QFileDialog.getExistingDirectory(self, "Select Comic Folder")
        if folder:
            self.current_folder = folder
            self.load_file_list()
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
            files = sorted([
                f for f in os.listdir(self.current_folder)
                if os.path.splitext(f)[1].lower() in valid_exts
            ])
            # 添加到列表控件
            self.file_list.addItems(files)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load folder: {e}")
    
    def load_image(self, item):
        """
        加载图片到画布
        
        当用户点击文件列表中的某个文件时调用
        
        参数:
            item: 点击的列表项（QListWidgetItem）
        """
        file_name = item.text()
        file_path = os.path.join(self.current_folder, file_name)
        self.status_bar.showMessage(f"Selected: {file_name}")
        self.canvas.load_image(file_path)
    
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
        弹出确认对话框，用户确认后开始OCR和翻译
        
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
        self.status_bar.showMessage("Processing selection...")
        self.ocr_text_edit.setText("Processing...")
        self.trans_text_edit.clear()
        
        # 保存临时文件（使用持久临时文件，线程可以读取）
        try:
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, "pact_crop.png")
            pixmap.save(temp_path, "PNG")
            
            # 启动翻译工作线程
            self.worker = TranslationWorker(temp_path, context=self.current_context)
            # 连接信号（线程完成时更新UI）
            self.worker.status.connect(self.status_bar.showMessage)
            self.worker.finished.connect(self.on_translation_finished)
            self.worker.error.connect(self.on_translation_error)
            self.worker.start()  # 启动线程
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save temp image: {e}")
    
    def on_translation_finished(self, ocr_text, trans_text):
        """
        翻译完成回调函数
        
        当TranslationWorker完成翻译后，此方法被调用
        
        参数:
            ocr_text:   OCR识别结果
            trans_text: LLM翻译结果
        """
        self.ocr_text_edit.setText(ocr_text)
        
        if isinstance(trans_text, str):
            # 规范化换行符（处理不同来源的换行符格式）
            normalized = trans_text.replace("\r\n", "\n")
            normalized = normalized.replace("\r", "\n")
            normalized = normalized.replace("\\r\\n", "\n").replace("\\n", "\n")
            
            # 去除可能的引号包裹
            if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in ["'", '"']:
                normalized = normalized[1:-1]

            lines = normalized.split("\n")
            if len(lines) > 1:
                quote_chars = set(['"', "'", "“", "”", "「", "」", "『", "』", "《", "》", "‹", "›", "«", "»"])

                def is_quote_only(s: str) -> bool:
                    stripped = s.strip()
                    return bool(stripped) and all(ch in quote_chars for ch in stripped)

                enhanced_lines = []
                for i, line in enumerate(lines):
                    enhanced_lines.append(line)
                    if i >= len(lines) - 1:
                        continue
                    cur = line.strip()
                    nxt = lines[i + 1].strip()
                    if not cur or not nxt:
                        continue
                    if is_quote_only(cur) or is_quote_only(nxt):
                        continue
                    enhanced_lines.append("")
                normalized = "\n".join(enhanced_lines)
            
            self.trans_text_edit.setText(normalized)
        else:
            # 如果不是字符串，转换为字符串
            self.trans_text_edit.setText(str(trans_text))
        
        self.status_bar.showMessage("Translation Complete", 5000)
    
    def on_translation_error(self, error_msg):
        """
        翻译错误回调函数
        
        当TranslationWorker发生错误时，此方法被调用
        
        参数:
            error_msg: 错误信息
        """
        if error_msg == "__OCR_NO_TEXT__":
            # 特殊处理：未检测到文字
            msg = "未检测到文字：请重新框选更清晰/更大的区域，或在 Settings 启用 Vision。"
            self.status_bar.showMessage(f"Error: {msg}", 8000)
            self.ocr_text_edit.setText(msg)
            return
        
        # 其他错误
        self.status_bar.showMessage(f"Error: {error_msg}")
        QMessageBox.warning(self, "Task Failed", error_msg)
        self.ocr_text_edit.setText("Error")
    
    def warmup_ocr(self):
        """
        预热OCR引擎
        
        检查OCR引擎是否已初始化，如果没有则启动初始化线程
        """
        if getattr(ocr_engine, "initialized", False):
            self.status_bar.showMessage("OCR 已就绪", 3000)
            return
        
        # 如果已经在预热中，不再重复启动
        if self.ocr_init_worker and self.ocr_init_worker.isRunning():
            self.status_bar.showMessage("OCR 预热中...", 3000)
            return
        
        # 禁用预热按钮，防止重复点击
        if self.ocr_init_action:
            self.ocr_init_action.setEnabled(False)
        
        self.status_bar.showMessage("OCR 预热中...")
        self.ocr_init_worker = OcrInitWorker()
        self.ocr_init_worker.finished.connect(self.on_ocr_warmup_finished)
        self.ocr_init_worker.start()
    
    def on_ocr_warmup_finished(self, ok: bool, error_msg: str):
        """
        OCR预热完成回调
        
        参数:
            ok:         是否初始化成功
            error_msg:  错误信息（如果失败）
        """
        if self.ocr_init_action:
            self.ocr_init_action.setEnabled(True)
        
        if ok:
            self.status_bar.showMessage("OCR 预热完成", 5000)
            return
        
        # 预热失败
        msg = "OCR 预热失败"
        if error_msg:
            msg = f"{msg}: {error_msg}"
        self.status_bar.showMessage(msg, 8000)
