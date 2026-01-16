#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - OCR光学字符识别引擎模块

本模块实现了漫画文字识别功能，使用PaddleOCR进行英文文字识别。

主要功能：
1. 初始化PaddleOCR引擎（懒加载，单例模式）
2. 识别图片中的英文文字
3. 多种识别策略（标准模式、宽松模式、图像增强）
4. 兼容不同版本的PaddleOCR API

技术特点：
- 单例模式：整个应用共享一个OCR引擎实例
- 懒加载：第一次使用时才加载模型
- 多策略识别：标准识别失败后尝试宽松识别
- 图像增强：自动放大和填充图片提高识别率

依赖：
- paddlepaddle: 百度深度学习框架
- paddleocr: PaddleOCR OCR工具包
- pillow: Python图片处理库
"""

# ============================================================================
# 标准库导入
# ============================================================================
import os           # 操作系统功能（环境变量、文件操作）
import sys          # 系统功能
import logging      # 日志记录
import tempfile     # 临时文件操作

# ============================================================================
# PaddleOCR 环境配置
# ============================================================================
# 在导入PaddleOCR之前设置环境变量，优化性能和兼容性
# 这些设置可以避免一些底层警告和性能问题
# 
# FLAGS_allocator_strategy: 内存分配策略，'auto_growth'动态增长
# DISABLE_MODEL_SOURCE_CHECK: 禁用模型来源检查
# FLAGS_use_mkldnn: 禁用MKL-DNN（Intel数学核心库）
# FLAGS_use_xdnn: 禁用XDNN
# FLAGS_enable_pir_api: 禁用新的PIR API（兼容性）
# FLAGS_enable_pir_in_executor: 禁用执行器中的PIR
# ============================================================================
os.environ['FLAGS_allocator_strategy'] = 'auto_growth'
os.environ.setdefault('DISABLE_MODEL_SOURCE_CHECK', 'True')
os.environ.setdefault('FLAGS_use_mkldnn', '0')
os.environ.setdefault('FLAGS_use_xdnn', '0')
os.environ.setdefault('FLAGS_enable_pir_api', '0')
os.environ.setdefault('FLAGS_enable_pir_in_executor', '0')


# ============================================================================
# OCREngine 类 - OCR识别引擎
# ============================================================================
# 封装PaddleOCR的所有操作
#
# 设计模式：
# - 单例模式：确保整个应用只有一个OCR引擎实例
#   （避免重复加载模型，节省内存和时间）
# - 懒加载：直到真正需要时才初始化引擎
#
# 为什么使用单例？
# - OCR模型很大，加载需要几秒钟
# - 多次初始化会浪费内存
# - 整个应用只需要一个识别器
# ============================================================================
class OCREngine:
    """
    OCR光学字符识别引擎类
    
    使用PaddleOCR进行英文文字识别，支持多种识别策略。
    
    识别流程：
    1. 首次使用时初始化PaddleOCR
    2. 调用recognize()进行识别
    3. 如果标准识别失败，尝试宽松识别
    4. 如果仍然失败，尝试图像增强后识别
    
    属性：
        ocr: PaddleOCR实例
        initialized: 是否已初始化
    """
    
    # 类变量，用于实现单例模式
    _instance = None
    
    def __new__(cls):
        """
        单例模式的实现
        
        确保整个应用只有一个OCREngine实例
        
        工作原理：
        1. 第一次创建时，_instance为None
        2. 调用父类的__new__创建实例
        3. 初始化ocr为None，initialized为False
        4. 返回这个唯一实例
        
        后续调用直接返回已创建的实例
        """
        if cls._instance is None:
            cls._instance = super(OCREngine, cls).__new__(cls)
            cls._instance.ocr = None
            cls._instance.initialized = False
        return cls._instance
    
    def initialize(self):
        """
        初始化PaddleOCR引擎
        
        首次调用时加载OCR模型，后续调用直接返回True
        
        返回:
            bool: 初始化是否成功
            
        配置说明：
        - lang='en': 识别英文
        - device='cpu': 使用CPU（也可以设为'cuda'使用GPU）
        - enable_mkldnn=False: 禁用MKL-DNN加速
        - enable_cinn=False: 禁用CINN
        - 其他参数禁用文档方向分类等不需要的功能
        """
        if self.initialized:
            return True
        
        try:
            from paddleocr import PaddleOCR
            import logging
            
            # 设置PaddleOCR日志级别为ERROR，减少控制台输出
            logging.getLogger("ppocr").setLevel(logging.ERROR)
            
            # 创建PaddleOCR实例
            self.ocr = PaddleOCR(
                lang='en',                          # 英文识别
                device='cpu',                       # 使用CPU
                enable_mkldnn=False,                # 禁用MKL-DNN
                enable_cinn=False,                  # 禁用CINN
                use_doc_orientation_classify=False, # 禁用文档方向分类
                use_doc_unwarping=False,            # 禁用文档校正
                use_textline_orientation=False,     # 禁用文本行方向检测
            )
            
            self.initialized = True
            return True
            
        except ImportError:
            print("PaddleOCR not found. Please install it via pip install paddlepaddle paddleocr")
            return False
        except Exception as e:
            print(f"Failed to initialize PaddleOCR: {e}")
            return False
    
    def _extract_text(self, result):
        """
        从PaddleOCR的识别结果中提取文本
        
        PaddleOCR返回的结果格式复杂多变，这个函数处理各种可能的情况
        
        参数:
            result: PaddleOCR返回的识别结果
            
        返回:
            str: 提取的文本，多行以换行符分隔
            
        结果格式说明：
        PaddleOCR返回的结果可能是：
        1. 字符串：直接返回
        2. 字典：尝试从rec_texts、texts、text、result等键提取
        3. 列表：递归处理每个元素
        4. 嵌套结构：层层深入提取文本
        """
        if result is None:
            return ""
        
        # 1. 如果是字符串，直接返回
        if isinstance(result, str):
            return result.strip()
        
        # 2. 如果是字典，从常见键中提取
        if isinstance(result, dict):
            for key in ["rec_texts", "texts", "text", "result"]:
                value = result.get(key)
                if isinstance(value, list):
                    # 提取列表中的所有文本，用换行符连接
                    return "\n".join([str(x).strip() for x in value if str(x).strip()])
                if isinstance(value, str):
                    return value.strip()
            return ""
        
        # 3. 如果是列表
        if isinstance(result, list):
            if not result:
                return ""
            
            # 处理嵌套列表
            if len(result) == 1 and isinstance(result[0], list):
                result = result[0]
            
            lines = []
            
            for item in result:
                if item is None:
                    continue
                
                # 字符串类型
                if isinstance(item, str):
                    if item.strip():
                        lines.append(item.strip())
                    continue
                
                # 字典类型
                if isinstance(item, dict):
                    for key in ["rec_texts", "texts"]:
                        value = item.get(key)
                        if isinstance(value, list):
                            for x in value:
                                if isinstance(x, str) and x.strip():
                                    lines.append(x.strip())
                            if lines:
                                continue
                    
                    # 尝试从rec_text或text键提取
                    text = item.get("rec_text") or item.get("text")
                    if isinstance(text, str) and text.strip():
                        lines.append(text.strip())
                    continue
                
                # 列表或元组类型（常见于旧版PaddleOCR格式）
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    second = item[1]
                    if isinstance(second, (list, tuple)) and len(second) >= 1:
                        text = second[0]
                        if isinstance(text, str) and text.strip():
                            lines.append(text.strip())
            
            return "\n".join(lines)
        
        # 4. 其他情况返回空字符串
        return ""
    
    def recognize(self, image_path):
        """
        识别图片中的文字
        
        主入口函数，调用OCR进行文字识别
        
        参数:
            image_path: 图片文件路径
            
        返回:
            str: 识别出的文字，失败返回错误信息
            
        识别策略：
        1. 标准识别（默认参数）
        2. 如果失败，尝试宽松识别（降低阈值）
        3. 如果仍然失败，尝试图像增强（放大+白边填充）
        4. 多尺度识别（小图放大后识别）
        
        宽松模式说明：
        - text_det_thresh: 文字检测置信度阈值降低
        - text_det_box_thresh: 文字框置信度阈值降低
        - text_det_unclip_ratio: 文字框扩展比例增大
        - 这样可以检测到更多可能但不确定的文字
        """
        # 检查是否已初始化，未初始化则尝试初始化
        if not self.initialized:
            if not self.initialize():
                return "Error: PaddleOCR not initialized or not installed."
        
        try:
            # 检查图片文件是否存在
            if not os.path.exists(image_path):
                return ""
            
            # 定义内部识别函数
            def _predict(path: str, *, lenient: bool):
                """
                执行OCR预测
                
                参数:
                    path: 图片路径
                    lenient: 是否使用宽松模式
                    
                返回:
                    识别结果
                """
                # 检查API版本，使用新版predict还是旧版ocr
                if not hasattr(self.ocr, "predict"):
                    return self.ocr.ocr(path)
                
                # 构建参数
                kwargs = {
                    "use_doc_orientation_classify": False,
                    "use_doc_unwarping": False,
                    "use_textline_orientation": False,
                }
                
                # 宽松模式使用更低的阈值
                if lenient:
                    kwargs.update(
                        {
                            "text_det_thresh": 0.15,           # 检测阈值
                            "text_det_box_thresh": 0.25,       # 框置信度
                            "text_det_unclip_ratio": 2.2,       # 框扩展比例
                            "text_rec_score_thresh": 0.15,      # 识别置信度
                            "text_det_limit_type": "max",       # 检测尺寸限制类型
                            "text_det_limit_side_len": 2560,    # 最大边限制
                        }
                    )
                
                return self.ocr.predict(path, **kwargs)
            
            # ===== 策略1：标准识别 =====
            if hasattr(self.ocr, "predict"):
                result = _predict(image_path, lenient=False)
                text = self._extract_text(result)
                if text.strip():
                    return text
            
            else:
                result = self.ocr.ocr(image_path)
                text = self._extract_text(result)
                if text.strip():
                    return text
            
            # ===== 策略2：宽松识别（降低阈值） =====
            if hasattr(self.ocr, "predict"):
                result = _predict(image_path, lenient=True)
                text = self._extract_text(result)
                if text.strip():
                    return text
            
            # ===== 策略3：图像增强识别 =====
            try:
                from PIL import Image, ImageOps
                
                with Image.open(image_path) as im:
                    # 转换为RGB（处理PNG等格式）
                    im = im.convert("RGB")
                    w, h = im.size
                    
                    # 检查图片尺寸是否有效
                    if w <= 0 or h <= 0:
                        return ""
                    
                    # 添加白边（padding）
                    # 这样可以避免边缘文字被截断
                    pad = max(10, int(min(w, h) * 0.08))
                    im = ImageOps.expand(im, border=pad, fill=(255, 255, 255))
                    
                    # 根据图片大小决定放大倍数
                    max_side = max(im.size)
                    scales = []
                    if max_side < 700:
                        scales = [2, 3]      # 小图放大2-3倍
                    elif max_side < 1100:
                        scales = [2]         # 中图放大2倍
                    
                    # 多尺度识别
                    for scale in scales:
                        sw, sh = im.size[0] * scale, im.size[1] * scale
                        # 使用LANCZOS重采样（高质量缩小/放大）
                        sim = im.resize((sw, sh), resample=Image.Resampling.LANCZOS)
                        
                        tmp_path = None
                        try:
                            # 创建临时文件
                            fd, tmp_path = tempfile.mkstemp(prefix="pact_ocr_", suffix=".png")
                            os.close(fd)  # 关闭文件描述符
                            sim.save(tmp_path)
                            
                            # 识别临时文件
                            if hasattr(self.ocr, "predict"):
                                result = _predict(tmp_path, lenient=True)
                                text = self._extract_text(result)
                                if text.strip():
                                    return text
                            else:
                                result = self.ocr.ocr(tmp_path)
                                text = self._extract_text(result)
                                if text.strip():
                                    return text
                        finally:
                            # 清理临时文件
                            if tmp_path and os.path.exists(tmp_path):
                                try:
                                    os.unlink(tmp_path)
                                except OSError:
                                    pass
            except Exception:
                pass  # 图像增强失败时静默处理
            
            # 所有策略都失败，返回空字符串
            return ""
            
        except Exception as e:
            return f"OCR Error: {str(e)}"


# ============================================================================
# 全局单例实例
# ============================================================================
# 创建全局唯一的OCR引擎实例
ocr_engine = OCREngine()
