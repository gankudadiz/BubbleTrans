#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - 图片画布模块

本模块实现了漫画显示翻译器的图片和框选功能。

核心功能：
1. 图片显示 - 使用QGraphicsView展示漫画图片，支持缩放和平移
2. 图片平移 - 鼠标左键拖动平移图片
3. 区域框选 - 鼠标右键拖动选择要翻译的区域
4. 滚轮缩放 - 使用鼠标滚轮缩放图片

技术实现：
- QGraphicsView: 提供可滚动的图片查看区域
- QGraphicsScene: 管理场景中的图形项
- QRubberBand: 显示框选时的矩形选框
- 坐标映射: 视口坐标与场景坐标之间的转换

鼠标操作：
- 左键拖动：平移图片
- 右键拖动：框选翻译区域
- 滚轮滚动：缩放图片
"""

# ============================================================================
# PyQt6 框架导入
# ============================================================================
# 从QtWidgets导入图形视图和场景相关组件
from PyQt6.QtWidgets import (
    QGraphicsView,      # 图形视图控件，提供查看和操作图形场景的界面
    QGraphicsScene,     # 图形场景，管理图形项的容器
    QGraphicsPixmapItem, # 图形项，用于显示图片
    QGraphicsTextItem,  # 图形文本项，用于显示占位文字
    QRubberBand,        # 橡皮筋选择框，显示矩形选区
    QPushButton,        # 按钮控件（导航箭头）
    QLabel,             # 标签控件（页码指示器）
    QWidget             # 基础窗口部件
)

# 从QtCore导入核心功能和信号
from PyQt6.QtCore import (
    Qt,                # 常量定义（如对齐方式、鼠标按钮等）
    QRectF,            # 浮点矩形，用于场景坐标
    QPoint,            # 坐标点类
    pyqtSignal,        # 信号定义
    QSize,             # 尺寸类
    QRect,             # 整数矩形
    QTimer             # 定时器（导航按钮延时隐藏）
)

# 从QtGui导入图形相关类
from PyQt6.QtGui import (
    QPixmap,           # 图片类，用于显示图像数据
    QPainter,          # 画家类，用于渲染设置
    QWheelEvent,       # 滚轮事件
    QMouseEvent,       # 鼠标事件
    QKeyEvent          # 键盘事件（方向键翻页）
)


# ============================================================================
# ImageCanvas 类 - 图片画布
# ============================================================================
# 继承自QGraphicsView，提供图片显示和区域选择功能
#
# 坐标系说明：
# - 视口坐标（Viewport Coordinates）：屏幕上显示区域的坐标
# - 场景坐标（Scene Coordinates）：图片内部的坐标（与图片像素对应）
#
# 状态标记：
# - has_user_transform: 标记用户是否进行过缩放操作
#                       如果为True，窗口调整大小时保持当前缩放比例
#                       如果为False，自动适应窗口大小
# ============================================================================
class ImageCanvas(QGraphicsView):
    """
    图片画布类 - 显示漫画图片并支持区域框选
    
    功能：
    - 显示加载的图片
    - 支持鼠标滚轮缩放
    - 支持右键框选翻译区域
    - 支持左键平移图片
    - 窗口大小改变时自动调整或保持缩放
    
    信号：
    - region_selected: 当用户完成框选时发射，携带裁剪后的图片(QPixmap)
    """
    
    # 定义信号：当完成区域选择时发射，参数为裁剪后的图片
    region_selected = pyqtSignal(QPixmap)
    
    # 导航信号：前后翻页（由 MainWindow 连接处理）
    nav_prev = pyqtSignal()
    nav_next = pyqtSignal()
    
    def __init__(self, parent=None):
        """
        初始化图片画布
        
        设置图形场景、渲染属性、选择状态等
        
        参数:
            parent: 父窗口部件
        """
        super().__init__(parent)
        
        # ===== 场景设置 =====
        # 创建图形场景，用于管理图片项
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        # 图片项和当前图片
        self.pixmap_item = None        # QGraphicsPixmapItem实例
        self.current_pixmap = None     # 当前加载的QPixmap
        
        # 用户变换标记
        # False: 窗口调整大小时自动适应图片
        # True:  窗口调整大小时保持当前缩放比例
        self.has_user_transform = False
        
        # ===== 渲染设置 =====
        # 抗锯齿渲染，使图片边缘更平滑
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 平滑像素变换，缩放时保持图片质量
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        # 拖拽模式 - NoDrag表示不响应拖拽（我们自定义处理）
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        
        # 变换锚点设置
        # ViewportAnchor.AnchorViewCenter: 以视图中心为缩放/调整中心
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        
        # 隐藏滚动条（使用自己的平移逻辑）
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # 设置背景色为深灰色
        self.setBackgroundBrush(Qt.GlobalColor.darkGray)
        
        # 图片居中显示
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # ===== 框选状态 =====
        self.is_selecting = False       # 是否正在框选
        self.origin = QPoint()          # 框选的起点坐标
        
        # 创建橡皮筋选择框（显示框选区域）
        self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        
        # ===== 平移状态 =====
        self.is_panning = False         # 是否正在平移
        self.pan_start = QPoint()       # 平移开始时的鼠标位置
        
        # ===== 导航覆盖层 =====
        # 按钮仅做键盘方向键翻页，不显示 UI 控件
        self._btn_prev = None
        self._btn_next = None
        self._lbl_page = None
        self._nav_visible = False
        self._nav_hide_timer = None
        
        # 接受键盘焦点，以支持左右方向键翻页
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    
    def load_image(self, image_path, pixmap=None):
        """
        加载图片
        
        清除当前场景中的内容，加载新图片并适应窗口大小
        
        参数:
            image_path: 图片文件的路径（绝对路径或相对路径）
            pixmap:     可选，预解码好的QPixmap（用于缓存命中场景）
                        为None时从文件路径同步解码
            
        操作步骤：
        1. 清空场景
        2. 重置变换（缩放比例）
        3. 加载图片（优先使用传入的pixmap，否则从文件解码）
        4. 创建图形项添加到场景
        5. 设置场景大小为图片大小
        6. 缩放以适应窗口（保持宽高比）
        7. 居中显示图片
        """
        self.scene.clear()              # 清除场景中所有图形项
        self.resetTransform()           # 重置所有变换（缩放、旋转等）
        self.has_user_transform = False # 重置用户变换标记
        
        # 加载图片：优先使用缓存的pixmap，否则从文件解码
        if pixmap is not None:
            self.current_pixmap = pixmap
        else:
            self.current_pixmap = QPixmap(image_path)
        self._current_image_path = image_path  # 存储当前图片路径
        
        # 创建图片图形项并添加到场景
        self.pixmap_item = QGraphicsPixmapItem(self.current_pixmap)
        self.scene.addItem(self.pixmap_item)
        
        # 设置场景矩形为图片的边界矩形
        self.setSceneRect(self.pixmap_item.boundingRect())
        
        # 缩放以适应视图，保持宽高比
        self.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        
        # 居中显示图片
        self.centerOn(self.pixmap_item)
    
    def show_placeholder(self, text="加载中…"):
        """
        显示占位文字（在异步解码期间展示）
        
        清空场景并居中显示提示文字，避免"白屏等待"的体验
        
        参数:
            text: 提示文字内容
        """
        self.scene.clear()
        self.resetTransform()
        self.has_user_transform = False
        self.current_pixmap = None
        self.pixmap_item = None
        self._current_image_path = None
        
        # 创建居中文本项
        text_item = QGraphicsTextItem(text)
        font = text_item.font()
        font.setPointSize(18)
        text_item.setFont(font)
        text_item.setDefaultTextColor(Qt.GlobalColor.white)
        self.scene.addItem(text_item)
        
        # 以文本边界设置场景矩形并居中
        self.setSceneRect(self.scene.itemsBoundingRect())
        self.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.centerOn(text_item)
        # 占位时隐藏页码指示器
        if self._lbl_page is not None:
            self._lbl_page.hide()
    
    # ===================== 导航覆盖层 =====================
    
    def _setup_nav_overlay(self):
        """创建半透明导航按钮和页码指示器（浮在画布上方）"""
        viewport = self.viewport()
        
        # 设置画布的鼠标追踪（用于 hover 显示导航按钮）
        self.setMouseTracking(True)
        
        # --- 前翻按钮 ---
        self._btn_prev = QPushButton("<", viewport)
        self._btn_prev.setFixedSize(44, 44)
        self._btn_prev.setCursor(Qt.CursorShape.ArrowCursor)
        self._btn_prev.clicked.connect(self.nav_prev.emit)
        
        # --- 后翻按钮 ---
        self._btn_next = QPushButton(">", viewport)
        self._btn_next.setFixedSize(44, 44)
        self._btn_next.setCursor(Qt.CursorShape.ArrowCursor)
        self._btn_next.clicked.connect(self.nav_next.emit)
        
        # --- 页码指示器 ---
        self._lbl_page = QLabel("", viewport)
        self._lbl_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # --- 统一样式 ---
        self._apply_nav_styles()
        
        # --- 初始隐藏，hover 时浮现 ---
        self._nav_visible = False
        self._btn_prev.hide()
        self._btn_next.hide()
        self._lbl_page.hide()
        
        # --- 延时隐藏定时器 ---
        self._nav_hide_timer = QTimer(self)
        self._nav_hide_timer.setSingleShot(True)
        self._nav_hide_timer.timeout.connect(self._hide_nav_overlay)
        
        # --- 位置更新 ---
        self._reposition_nav_overlay()
    
    def _apply_nav_styles(self):
        """为导航按钮和页码指示器应用统一样式表（避免 rgba 确保兼容性）"""
        btn_style = """
        QPushButton {
            background-color: #1e1e1e;
            color: #cccccc;
            border: 1px solid #555555;
            border-radius: 22px;
            font-size: 18px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #3a3a3a;
            color: #ffffff;
            border: 1px solid #888888;
        }
        QPushButton:pressed {
            background-color: #505050;
        }
        QPushButton:disabled {
            background-color: #1a1a1a;
            color: #444444;
            border: 1px solid #333333;
        }
        """
        lbl_style = """
        QLabel {
            background-color: #1e1e1e;
            color: #cccccc;
            border-radius: 10px;
            padding: 4px 12px;
            font-size: 13px;
        }
        """
        self._btn_prev.setStyleSheet(btn_style)
        self._btn_next.setStyleSheet(btn_style)
        self._lbl_page.setStyleSheet(lbl_style)
    
    def _reposition_nav_overlay(self):
        """根据视口大小重新定位导航按钮和页码指示器"""
        if self._btn_prev is None:
            return
        vp = self.viewport()
        w, h = vp.width(), vp.height()
        self._btn_prev.move(10, (h - 44) // 2)
        self._btn_next.move(w - 54, (h - 44) // 2)
        self._lbl_page.adjustSize()
        lw = self._lbl_page.width()
        self._lbl_page.move((w - lw) // 2, h - 36)
    
    def _show_nav_overlay(self):
        """浮现导航按钮（鼠标进入画布时调用）"""
        if self._btn_prev is None:
            return
        if self._nav_visible:
            return
        self._nav_visible = True
        self._nav_hide_timer.stop()
        self._btn_prev.show()
        self._btn_next.show()
        if self._current_image_path:
            self._lbl_page.show()
    
    def _hide_nav_overlay(self):
        """隐藏导航按钮（鼠标离开画布 500ms 后调用）"""
        if self._btn_prev is None:
            return
        self._nav_visible = False
        self._btn_prev.hide()
        self._btn_next.hide()
        self._lbl_page.hide()
    
    def update_page_indicator(self, current: int, total: int):
        """更新页码指示器文本（"3 / 25" 格式）"""
        if self._lbl_page is None:
            return
        self._lbl_page.setText(f"{current} / {total}")
        self._reposition_nav_overlay()
        if self._nav_visible and self._current_image_path:
            self._lbl_page.show()
    
    # ===================== 事件处理 =====================
    
    def enterEvent(self, event):
        """鼠标进入画布：浮现导航覆盖层"""
        if self._btn_prev is not None:
            self._show_nav_overlay()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """鼠标离开画布：延时隐藏导航覆盖层"""
        if self._btn_prev is not None:
            self._nav_hide_timer.start(500)
        super().leaveEvent(event)
    
    def keyPressEvent(self, event: QKeyEvent):
        """键盘事件：左右方向键翻页，Esc 取消框选"""
        # Esc 键取消框选
        if event.key() == Qt.Key.Key_Escape:
            if self.is_selecting:
                self.rubber_band.hide()
                self.is_selecting = False
                event.accept()
                return
            # 未在框选时不做处理，交由父类处理
        if event.key() == Qt.Key.Key_Left:
            self.nav_prev.emit()
        elif event.key() == Qt.Key.Key_Right:
            self.nav_next.emit()
        else:
            super().keyPressEvent(event)
    
    def wheelEvent(self, event: QWheelEvent):
        """
        滚轮事件处理 - 缩放图片
        
        当用户滚动鼠标滚轮时，缩放当前图片
        
        参数:
            event: 滚轮事件对象
            
        缩放逻辑：
        - 向上滚动（angleDelta().y() > 0）：放大，缩放因子1.25
        - 向下滚动：缩小，缩放因子0.8
        - 以当前视图中心为缩放中心
        """
        # 如果没有加载图片，直接返回
        if not self.pixmap_item:
            return
        
        # 标记用户已进行过缩放操作
        self.has_user_transform = True
        
        # 获取视图中心在场景中的坐标（缩放中心）
        view_center = self.mapToScene(self.viewport().rect().center())
        
        # 判断滚轮方向
        zoom_in = event.angleDelta().y() > 0
        factor = 1.25 if zoom_in else 0.8
        
        # 执行缩放
        self.scale(factor, factor)
        
        # 以原视图中心为锚点缩放
        self.centerOn(view_center)
    
    def mousePressEvent(self, event: QMouseEvent):
        """
        鼠标按下事件处理
        
        根据鼠标按钮启动不同的操作：
        - 左键：开始平移
        - 右键：开始框选
        
        参数:
            event: 鼠标事件对象
        """
        if event.button() == Qt.MouseButton.LeftButton:
            # ===== 左键：开始平移 =====
            self.is_panning = True
            self.pan_start = event.pos()  # 记录起点
            self.setCursor(Qt.CursorShape.ClosedHandCursor)  # 切换光标为抓手
            event.accept()
            
        elif event.button() == Qt.MouseButton.RightButton:
            # ===== 右键：开始框选 =====
            self.is_selecting = True
            self.origin = event.pos()  # 记录起点位置
            # 设置橡皮筋的位置和大小
            self.rubber_band.setGeometry(QRect(self.origin, QSize()))
            self.rubber_band.show()    # 显示橡皮筋
            event.accept()
            
        else:
            # 其他鼠标按钮，调用父类默认处理
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """
        鼠标移动事件处理
        
        根据当前状态更新界面：
        - 框选中：更新橡皮筋的大小和位置
        - 平移中：移动图片位置
        
        参数:
            event: 鼠标事件对象
        """
        if self.is_selecting:
            # ===== 框选中：更新橡皮筋 =====
            # normalized()确保矩形左上角在右下角之前
            self.rubber_band.setGeometry(QRect(self.origin, event.pos()).normalized())
            event.accept()
            
        elif self.is_panning:
            # ===== 平移中：移动图片 =====
            self.has_user_transform = True
            
            # 计算移动距离
            delta = event.pos() - self.pan_start
            self.pan_start = event.pos()  # 更新起点
            
            # 调整滚动条位置（实现图片平移效果）
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            h_bar.setValue(h_bar.value() - delta.x())
            v_bar.setValue(v_bar.value() - delta.y())
            event.accept()
            
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """
        鼠标释放事件处理
        
        完成当前操作：
        - 右键释放：完成框选，提取选区并发射信号
        - 左键释放：结束平移
        
        参数:
            event: 鼠标事件对象
        """
        if event.button() == Qt.MouseButton.RightButton and self.is_selecting:
            # ===== 右键释放：完成框选 =====
            self.is_selecting = False
            self.rubber_band.hide()  # 隐藏橡皮筋
            
            # 获取橡皮筋在视口中的矩形
            rect = self.rubber_band.geometry()
            
            # 将视口坐标转换为场景坐标
            # mapToScene()将QRect转换为QPolygonF
            scene_rect = self.mapToScene(rect).boundingRect()
            
            # 裁剪图片
            if self.current_pixmap and not scene_rect.isEmpty():
                # 获取图片在场景中的边界矩形
                img_rect = self.pixmap_item.boundingRect()
                
                # 计算选区与图片的交集（确保选区在图片范围内）
                intersection = scene_rect.intersected(img_rect)
                
                if not intersection.isEmpty():
                    # 裁剪图片
                    # QPixmap.copy()需要整数坐标，所以用toRect()转换
                    cropped = self.current_pixmap.copy(intersection.toRect())
                    
                    # 发射region_selected信号，携带裁剪后的图片
                    self.region_selected.emit(cropped)
            
            event.accept()
            
        elif event.button() == Qt.MouseButton.LeftButton and self.is_panning:
            # ===== 左键释放：结束平移 =====
            self.is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)  # 恢复光标形状
            event.accept()
            
        else:
            super().mouseReleaseEvent(event)
    
    def resizeEvent(self, event):
        """
        窗口大小调整事件处理
        
        根据用户是否进行过缩放操作，决定如何调整显示：
        - 未缩放过：自动适应窗口大小
        - 已缩放过：保持当前缩放比例，只调整中心位置
        
        参数:
            event: 调整大小事件对象
        """
        view_center = None
        
        if self.pixmap_item:
            # 记录调整前的视图中心在场景中的位置
            view_center = self.mapToScene(self.viewport().rect().center())
        
        # 调用父类的resizeEvent
        super().resizeEvent(event)
        
        # 更新导航覆盖层位置（按钮 + 页码指示器）
        self._reposition_nav_overlay()
        
        if not self.pixmap_item:
            return
        
        if not self.has_user_transform:
            # 用户未缩放过，自动适应窗口
            self.resetTransform()
            self.setSceneRect(self.pixmap_item.boundingRect())
            self.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
            self.centerOn(self.pixmap_item)
            return
        
        # 用户已缩放过，保持缩放比例
        if view_center is not None:
            self.centerOn(view_center)
