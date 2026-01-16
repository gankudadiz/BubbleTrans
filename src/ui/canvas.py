#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - 图片画布模块

本模块实现了漫画显示翻译器的图片和框选功能。

核心功能：
1. 图片显示 - 使用QGraphicsView展示漫画图片，支持缩放和平移
2. 区域框选 - 鼠标左键拖动选择要翻译的区域
3. 图片平移 - 鼠标右键拖动平移图片
4. 滚轮缩放 - 使用鼠标滚轮缩放图片

技术实现：
- QGraphicsView: 提供可滚动的图片查看区域
- QGraphicsScene: 管理场景中的图形项
- QRubberBand: 显示框选时的矩形选框
- 坐标映射: 视口坐标与场景坐标之间的转换

鼠标操作：
- 左键拖动：框选翻译区域
- 右键拖动：平移图片
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
    QRubberBand,        # 橡皮筋选择框，显示矩形选区
    QWidget             # 基础窗口部件
)

# 从QtCore导入核心功能和信号
from PyQt6.QtCore import (
    Qt,                # 常量定义（如对齐方式、鼠标按钮等）
    QRectF,            # 浮点矩形，用于场景坐标
    QPoint,            # 坐标点类
    pyqtSignal,        # 信号定义
    QSize,             # 尺寸类
    QRect              # 整数矩形
)

# 从QtGui导入图形相关类
from PyQt6.QtGui import (
    QPixmap,           # 图片类，用于显示图像数据
    QPainter,          # 画家类，用于渲染设置
    QWheelEvent,       # 滚轮事件
    QMouseEvent        # 鼠标事件
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
    - 支持左键框选翻译区域
    - 支持右键平移图片
    - 窗口大小改变时自动调整或保持缩放
    
    信号：
    - region_selected: 当用户完成框选时发射，携带裁剪后的图片(QPixmap)
    """
    
    # 定义信号：当完成区域选择时发射，参数为裁剪后的图片
    region_selected = pyqtSignal(QPixmap)
    
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
    
    def load_image(self, image_path):
        """
        加载图片
        
        清除当前场景中的内容，加载新图片并适应窗口大小
        
        参数:
            image_path: 图片文件的路径（绝对路径或相对路径）
            
        操作步骤：
        1. 清空场景
        2. 重置变换（缩放比例）
        3. 加载图片文件创建QPixmap
        4. 创建图形项添加到场景
        5. 设置场景大小为图片大小
        6. 缩放以适应窗口（保持宽高比）
        7. 居中显示图片
        """
        self.scene.clear()              # 清除场景中所有图形项
        self.resetTransform()           # 重置所有变换（缩放、旋转等）
        self.has_user_transform = False # 重置用户变换标记
        
        # 加载图片
        self.current_pixmap = QPixmap(image_path)
        
        # 创建图片图形项并添加到场景
        self.pixmap_item = QGraphicsPixmapItem(self.current_pixmap)
        self.scene.addItem(self.pixmap_item)
        
        # 设置场景矩形为图片的边界矩形
        self.setSceneRect(self.pixmap_item.boundingRect())
        
        # 缩放以适应视图，保持宽高比
        self.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        
        # 居中显示图片
        self.centerOn(self.pixmap_item)
    
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
        - 左键：开始框选
        - 右键：开始平移
        
        参数:
            event: 鼠标事件对象
        """
        if event.button() == Qt.MouseButton.LeftButton:
            # ===== 左键：开始框选 =====
            self.is_selecting = True
            self.origin = event.pos()  # 记录起点位置
            # 设置橡皮筋的位置和大小
            self.rubber_band.setGeometry(QRect(self.origin, QSize()))
            self.rubber_band.show()    # 显示橡皮筋
            event.accept()             # 标记事件已处理
            
        elif event.button() == Qt.MouseButton.RightButton:
            # ===== 右键：开始平移 =====
            self.is_panning = True
            self.pan_start = event.pos()  # 记录起点
            self.setCursor(Qt.CursorShape.ClosedHandCursor)  # 切换光标为抓手
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
        - 左键释放：完成框选，提取选区并发射信号
        - 右键释放：结束平移
        
        参数:
            event: 鼠标事件对象
        """
        if event.button() == Qt.MouseButton.LeftButton and self.is_selecting:
            # ===== 左键释放：完成框选 =====
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
            
        elif event.button() == Qt.MouseButton.RightButton and self.is_panning:
            # ===== 右键释放：结束平移 =====
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
