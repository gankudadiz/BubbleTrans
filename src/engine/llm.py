#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - 大语言模型翻译引擎模块

本模块实现了与多模态LLM API的交互，直接识别图片中的文字并进行翻译。

主要功能：
1. 配置管理 - 从配置文件加载API密钥、模型、目标语言等设置
2. 图片翻译 - 直接将图片发送给多模态LLM，同时完成文字识别和翻译
3. 连接测试 - 测试API连接是否正常

支持的API：
- OpenRouter（推荐，支持多种模型）
- OpenAI官方API
- 兼容OpenAI API的其他服务

工作流程（v2.0）：
- 直接将图片发送给多模态LLM
- LLM同时完成文字识别和翻译
- 返回识别的原文和对应的译文

翻译规则：
1. 保持翻译简洁自然，适合漫画风格
2. 保留说话者的语气
3. 优先使用DC/Marvel的官方中文译名
4. 对于不确定的专有名词，保留原文或音译
5. 气泡内的拟声词（如"BAM""BOOM"）保留原样不翻译
"""

# ============================================================================
# 标准库导入
# ============================================================================
import os               # 操作系统功能（环境变量等）
import base64           # Base64编码解码（用于图片转码）
import re               # 正则表达式（用于解析LLM返回结果）
from io import BytesIO  # 内存中的二进制流（用于图片缩放）

# ============================================================================
# 第三方库导入
# ============================================================================
# OpenAI Python客户端，支持与OpenAI兼容的API服务通信
from openai import OpenAI

# ============================================================================
# 项目内部模块导入
# ============================================================================
# 加载配置文件的工具函数
from utils.config import load_config


# ============================================================================
# LLMEngine 类 - 大语言模型引擎
# ============================================================================
# 封装与LLM API的所有交互逻辑
#
# 使用方式：
# 1. 导入模块：from engine.llm import llm_engine
# 2. 配置API密钥：llm_engine.configure(api_key, base_url, model)
# 3. 设置目标语言：llm_engine.target_lang = "简体中文"
# 4. 调用翻译：origin_text, translated_text = llm_engine.translate_image(image_path)
#
# 设计模式：
# - 单例模式：全局只有一个llm_engine实例
# - 延迟初始化：直到需要时才创建OpenAI客户端
# ============================================================================
class LLMEngine:
    """
    大语言模型翻译引擎类
    
    负责与多模态LLM API通信，执行图片翻译任务。
    v2.0 将图片直接发送给多模态LLM，同时完成文字识别和翻译。
    
    属性：
        api_key: API密钥
        base_url: API服务器地址
        model: 使用的模型名称
        target_lang: 目标语言（如"简体中文"）
        use_vision: 是否启用Vision模式（始终为True）
        client: OpenAI客户端实例
    """
    
    # 语言标签映射：目标语言 -> XML 标签名
    LANG_TAG_MAP = {
        "简体中文": "中文",
        "繁體中文": "中文",
        "日本語": "日本語",
        "한국어": "한국어",
        "English": "English",
        "Français": "Français",
    }
    
    def __init__(self):
        """初始化LLM引擎，从配置文件加载设置"""
        # 默认配置
        self.api_key = ""                                       # API密钥
        self.base_url = "https://openrouter.ai/api/v1"          # 默认使用OpenRouter
        self.model = "google/gemini-2.0-flash-001"              # 默认模型
        self.target_lang = "简体中文"                            # 默认目标语言
        self.use_vision = True                                  # v2.0 始终使用Vision模式
        self.client = None                                      # OpenAI客户端实例
        
        # 从配置文件加载设置
        self._load_from_config()
    
    def _load_from_config(self):
        """
        从配置文件加载设置
        
        读取config.json中的API配置：
        - api_key: API密钥
        - base_url: API服务器地址
        - model: 模型名称
        - target_lang: 目标语言
        - use_vision: 是否启用Vision模式（兼容旧配置）
        
        如果配置有效，自动配置客户端
        """
        config = load_config()
        
        # 从配置获取设置，支持默认值
        self.api_key = config.get("api_key", "")
        self.base_url = config.get("base_url", "https://openrouter.ai/api/v1")
        self.model = config.get("model", "google/gemini-2.0-flash-001")
        self.target_lang = config.get("target_lang", "简体中文")
        
        # 兼容旧配置：如果配置中有 use_vision 字段则读取，否则默认为 True
        self.use_vision = config.get("use_vision", True)
        
        # 如果有API密钥，配置客户端
        if self.api_key:
            self.configure(self.api_key, self.base_url, self.model)
    
    def configure(self, api_key, base_url=None, model=None):
        """
        配置LLM引擎
        
        设置API密钥、服务器地址和模型，并创建OpenAI客户端
        
        参数:
            api_key: API密钥（必需）
            base_url: API服务器地址（可选）
            model: 模型名称（可选）
            
        关于OpenRouter：
        - OpenRouter是一个聚合多个LLM服务的平台
        - 需要特殊的HTTP头（HTTP-Referer和X-Title）用于统计
        """
        self.api_key = api_key
        
        # 更新服务器地址，去除末尾的斜杠，自动补 /v1
        if base_url:
            self.base_url = base_url.rstrip('/')
            # 自动补 /v1：如果 URL 只有域名没有路径（如 https://xxx.com），
            # 则补上 /v1，因为大多数 OpenAI 兼容代理使用 /v1 前缀
            from urllib.parse import urlparse
            parsed = urlparse(self.base_url)
            if (not parsed.path or parsed.path == '/') and '/v1' not in self.base_url:
                self.base_url += '/v1'
        
        # 更新模型名称
        if model:
            self.model = model
        
        # 如果有API密钥，创建OpenAI客户端
        if self.api_key:
            # 为OpenRouter设置特殊的HTTP头
            default_headers = None
            if "openrouter.ai" in self.base_url:
                default_headers = {
                    "HTTP-Referer": "https://github.com",
                    "X-Title": "BubbleTrans",
                }
            
            # 创建OpenAI客户端
            # 兼容任何支持OpenAI API格式的服务
            self.client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                default_headers=default_headers
            )
    
    def encode_image(self, image_path, max_size=2048):
        """
        将图片编码为Base64格式，自动缩放大图以加速传输
        
        用于将图片数据发送给多模态LLM API
        
        参数:
            image_path: 图片文件路径
            max_size: 图片最长边的最大像素数（默认2048，设0则不缩放）
            
        返回:
            Base64编码的字符串，失败返回None
        """
        if not os.path.exists(image_path):
            return None
        
        try:
            from PIL import Image
            img = Image.open(image_path)
            # 自动缩放：如果最长边超过 max_size，等比缩小
            if max_size > 0:
                w, h = img.size
                longest = max(w, h)
                if longest > max_size:
                    ratio = max_size / longest
                    new_size = (int(w * ratio), int(h * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
            # 转为 JPEG 字节流（压缩率 85，兼顾质量与体积）
            buffer = BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
        except Exception:
            # 降级：Pillow 处理失败时，回退到原始文件读取
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
    
    def _get_language_tag(self, target_lang):
        """
        获取目标语言对应的XML标签名
        
        参数:
            target_lang: 目标语言名称
            
        返回:
            XML标签名字符串
        """
        return self.LANG_TAG_MAP.get(target_lang, target_lang)
    
    def _build_system_prompt(self, target_lang):
        """
        构建系统提示词
        
        生成用于指导多模态LLM同时进行文字识别和翻译的系统提示词
        
        参数:
            target_lang: 目标语言（如"简体中文"）
            
        返回:
            系统提示词字符串
        """
        lang_tag = self._get_language_tag(target_lang)
        return f"""你是一个专业的漫画翻译助手。你的任务是：
1. 识别图片中所有文字，按阅读顺序整理成段落
2. 将原文翻译成{target_lang}

输出格式严格要求如下（不要添加任何额外说明）：

<原文>
段落一的内容…
段落二的内容…
</原文>

<{lang_tag}>
段落一的翻译…
段落二的翻译…
</{lang_tag}>

注意：
- 每个段落之间用空行分隔
- 原文和译文段落数量必须一一对应
- 气泡内的拟声词（如"BAM""BOOM"）保留原样不翻译
- 专有名词（人名、地名、组织等）：翻译为中文，并在其后用括号标注原文。不确定译名时保留原文
- 不确定的内容保留原文并标注[?]"""
    
    def _parse_response(self, response_text, target_lang):
        """
        解析LLM返回的结果
        
        从带XML标签的响应中提取原文和译文
        
        参数:
            response_text: LLM返回的原始文本
            target_lang: 目标语言
            
        返回:
            (origin_text, translated_text) 元组
            - origin_text: 识别到的原文文本（段落间 \n\n 分隔）
            - translated_text: 翻译后的译文文本（段落间 \n\n 分隔）
        """
        lang_tag = self._get_language_tag(target_lang)
        
        # 提取原文
        origin_match = re.search(r'<原文>\s*\n(.*?)</原文>', response_text, re.DOTALL)
        origin_text = origin_match.group(1).strip() if origin_match else ""
        
        # 提取译文
        trans_pattern = rf'<{re.escape(lang_tag)}>\s*\n(.*?)</{re.escape(lang_tag)}>'
        trans_match = re.search(trans_pattern, response_text, re.DOTALL)
        translated_text = trans_match.group(1).strip() if trans_match else ""
        
        return origin_text, translated_text
    
    def translate_image(self, image_path):
        """
        翻译图片中的文字
        
        直接将图片发送给多模态LLM，同时完成文字识别和翻译。
        这是v2.0的核心翻译方法，替代了旧的translate方法。
        
        参数:
            image_path: 图片文件路径
            
        返回:
            (origin_text, translated_text) 元组
            - origin_text: 识别的原文文本（段落间 \n\n 分隔）
            - translated_text: 译文文本（段落间 \n\n 分隔）
            
        失败时返回 ("", 错误信息)
        """
        # 检查客户端是否已配置
        if not self.client:
            return "", "Error: API not configured. Please go to Settings."
        
        # 检查图片文件是否存在
        if not os.path.exists(image_path):
            return "", f"Error: Image file not found: {image_path}"
        
        # ===== 构建系统提示词 =====
        system_prompt = self._build_system_prompt(self.target_lang)
        
        # ===== 编码图片 =====
        base64_image = self.encode_image(image_path)
        if not base64_image:
            return "", f"Error: Failed to encode image: {image_path}"
        
        # ===== 构建消息列表 =====
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ]
        
        # ===== 调用API =====
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=2048
            )
            
            response_text = response.choices[0].message.content
            
            # 解析返回结果
            origin_text, translated_text = self._parse_response(response_text, self.target_lang)
            
            return origin_text, translated_text
            
        except Exception as e:
            return "", f"API Error: {str(e)}"
    
    def test_connection(self, api_key, base_url, model):
        """
        测试API连接
        
        用于设置对话框中测试API配置是否正确
        
        参数:
            api_key: API密钥
            base_url: API服务器地址
            model: 模型名称
            
        返回:
            (成功与否, 详细信息)
            - 成功：返回(True, 连接成功信息)
            - 失败：返回(False, 详细错误信息和调试建议)
            
        调试信息包括：
        - 目标URL和模型
        - API密钥掩码（只显示前后4位）
        - 代理设置
        - 完整的错误信息和堆栈跟踪
        - 手动测试命令（curl）
        """
        import traceback
        import json
        
        debug_info = []  # 收集调试信息
        
        try:
            # 清理URL
            clean_base_url = base_url.rstrip('/')
            
            # ===== 收集调试信息 =====
            debug_info.append("=== Debug Information ===")
            debug_info.append(f"Target URL: {clean_base_url}")
            debug_info.append(f"Model: {model}")
            # 只显示API密钥的前后几位，中间用星号代替
            debug_info.append(f"API Key: {api_key[:4]}...{api_key[-4:] if len(api_key) > 8 else '****'}")
            
            # 检查代理设置
            http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
            https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
            debug_info.append(f"HTTP_PROXY: {http_proxy}")
            debug_info.append(f"HTTPS_PROXY: {https_proxy}")
            
            # 为OpenRouter设置特殊头
            default_headers = None
            if "openrouter.ai" in clean_base_url:
                default_headers = {
                    "HTTP-Referer": "https://github.com",
                    "X-Title": "BubbleTrans",
                }
                debug_info.append(f"Headers: {json.dumps(default_headers)}")
            
            # 创建临时客户端进行测试（设置较短的超时时间）
            test_client = OpenAI(
                base_url=clean_base_url,
                api_key=api_key,
                default_headers=default_headers,
                timeout=10.0  # 10秒超时
            )
            
            debug_info.append("Attempting chat completion...")
            
            # 发送最简单的测试请求
            response = test_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5  # 只返回5个token
            )
            
            debug_info.append("Response received.")
            # 容错：某些代理返回非标准格式
            content = getattr(response, 'choices', None)
            if content is not None:
                debug_info.append(f"Content: {response.choices[0].message.content}")
            else:
                debug_info.append(f"Raw response: {str(response)[:200]}")
            
            return True, "Connection successful!\n\n" + "\n".join(debug_info)
            
        except Exception as e:
            # 收集错误信息
            error_msg = f"Connection failed: {str(e)}"
            debug_info.append(f"ERROR: {str(e)}")
            debug_info.append("=== Traceback ===")
            debug_info.append(traceback.format_exc())
            
            # 生成curl命令，用于手动测试
            curl_cmd = f'curl.exe -v "{clean_base_url}/chat/completions" -H "Authorization: Bearer {api_key}" -H "Content-Type: application/json" -d "{{\\"model\\": \\"{model}\\", \\"messages\\": [{{\\"role\\": \\"user\\": \\"content\\": \\"Hi\\"}}]}}"'
            debug_info.append("\n=== Manual Test Command (PowerShell) ===")
            debug_info.append("You can try running this command in terminal to check network:")
            debug_info.append(curl_cmd)
            
            return False, "\n".join(debug_info)


# ============================================================================
# 全局单例实例
# ============================================================================
# 创建全局唯一的LLM引擎实例
# 这样整个应用只需要一个客户端连接
llm_engine = LLMEngine()
