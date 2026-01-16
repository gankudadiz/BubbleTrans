#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - 大语言模型翻译引擎模块

本模块实现了与LLM API的交互，用于将OCR识别的英文文本翻译成中文。

主要功能：
1. 配置管理 - 从配置文件加载API密钥、模型等设置
2. 文本翻译 - 调用LLM API进行文本翻译
3. 图片翻译 - 支持Vision模式，直接识别图片中的文字并进行翻译
4. 连接测试 - 测试API连接是否正常

支持的API：
- OpenRouter（推荐，支持多种模型）
- OpenAI官方API
- 兼容OpenAI API的其他服务

翻译规则：
1. 保持翻译简洁自然，适合漫画风格
2. 保留说话者的语气
3. 优先使用DC/Marvel的官方中文译名
4. 对于不确定的专有名词，保留原文或音译
"""

# ============================================================================
# 标准库导入
# ============================================================================
import os               # 操作系统功能（环境变量等）
import base64           # Base64编码解码（用于图片转码）

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
# 3. 调用翻译：result = llm_engine.translate(text, context, image_path, use_vision)
#
# 设计模式：
# - 单例模式：全局只有一个llm_engine实例
# - 延迟初始化：直到需要时才创建OpenAI客户端
# ============================================================================
class LLMEngine:
    """
    大语言模型翻译引擎类
    
    负责与LLM API通信，执行文本翻译任务。
    支持两种翻译模式：
    - 普通模式：先OCR识别文字，再翻译
    - Vision模式：直接识别图片中的文字并翻译
    
    属性：
        api_key: API密钥
        base_url: API服务器地址
        model: 使用的模型名称
        use_vision: 是否启用Vision模式
        client: OpenAI客户端实例
    """
    
    def __init__(self):
        """初始化LLM引擎，从配置文件加载设置"""
        # 默认配置
        self.api_key = ""                                       # API密钥
        self.base_url = "https://openrouter.ai/api/v1"          # 默认使用OpenRouter
        self.model = "google/gemini-2.0-flash-001"              # 默认模型
        self.use_vision = False                                 # 是否使用Vision模式
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
        - use_vision: 是否启用Vision模式
        
        如果配置有效，自动配置客户端
        """
        config = load_config()
        
        # 从配置获取设置，支持默认值
        self.api_key = config.get("api_key", "")
        self.base_url = config.get("base_url", "https://openrouter.ai/api/v1")
        self.model = config.get("model", "google/gemini-2.0-flash-001")
        self.use_vision = config.get("use_vision", False)
        
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
        
        # 更新服务器地址，去除末尾的斜杠
        if base_url:
            self.base_url = base_url.rstrip('/')
        
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
    
    def encode_image(self, image_path):
        """
        将图片编码为Base64格式
        
        用于Vision模式下将图片数据发送给LLM API
        
        参数:
            image_path: 图片文件路径
            
        返回:
            Base64编码的字符串，失败返回None
            
        注意：
        - 读取二进制模式打开文件
        - 使用base64编码后转为UTF-8字符串
        """
        if not os.path.exists(image_path):
            return None
        
        with open(image_path, "rb") as image_file:
            # 读取二进制数据 -> Base64编码 -> 解码为字符串
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def translate(self, text, context="", image_path=None, use_vision=False):
        """
        翻译文本或图片
        
        调用LLM API进行翻译，支持两种模式：
        - 普通模式：翻译传入的文本
        - Vision模式：识别图片中的文字并翻译
        
        参数:
            text: 要翻译的文本（普通模式）
            context: 漫画上下文信息（帮助LLM理解内容）
            image_path: 图片路径（Vision模式）
            use_vision: 是否使用Vision模式
            
        返回:
            翻译结果文本，失败返回错误信息
            
        提示词设计规则：
        1. 指定LLM扮演漫画翻译专家
        2. 提供漫画上下文
        3. 要求翻译简洁自然
        4. 保留说话语气
        5. 优先使用官方中文译名
        6. 不确定时保留原文
        """
        # 检查客户端是否已配置
        if not self.client:
            return "Error: API not configured. Please go to Settings."
        
        # ===== 构建系统提示词 =====
        # 告诉LLM如何进行漫画翻译
        system_prompt = f"""You are an expert American comic translator and localization editor.
Context about the comic: {context}

Task:
- Translate the input English (often OCR text) into fluent Simplified Chinese suitable for comic speech balloons.

Rules:
1. Prefer natural Chinese phrasing; do NOT translate word-for-word.
2. Maintain the speaker's tone, emotion, and rhythm.
3. Proper nouns: prioritize official DC/Marvel Chinese names (heroes, villains, organizations, locations, aliases). If uncertain, keep the original English (or transliterate).
4. OCR artifacts: treat line breaks and stray periods as layout markers, not sentence boundaries. Re-segment by meaning.
5. Output formatting:
   - Use standard Chinese punctuation（，。！？…）
   - Do NOT put every short phrase on its own line.
   - Only use line breaks to separate different speakers or different speech bubbles/paragraphs.
   - Inside a paragraph, do NOT insert manual line breaks.
   - If the text likely comes from multiple bubbles, merge into 1–2 coherent paragraphs when possible.
6. Return ONLY the translated text. No explanations. Do NOT wrap the whole output in quotes.
"""
        
        # ===== 构建消息列表 =====
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        user_content = []
        
        # ===== 构建用户消息 =====
        if isinstance(text, str) and text.strip():
            # 普通模式：翻译传入的文本
            user_content.append({
                "type": "text",
                "text": f"Original Text:\n{text}"
            })
        else:
            # 无文本时的情况
            if use_vision and image_path:
                # Vision模式：让LLM识别图片中的文字
                user_content.append({
                    "type": "text",
                    "text": "Please read the English text in the image and translate it to Simplified Chinese.",
                })
            else:
                user_content.append({"type": "text", "text": "Original Text:\n"})
        
        # ===== 添加图片（Vision模式） =====
        if use_vision and image_path:
            # 将图片编码为Base64
            base64_image = self.encode_image(image_path)
            if base64_image:
                # 添加图片到用户消息
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        # data:image/jpeg;base64,... 是标准的图片嵌入格式
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                })
        
        # 添加用户消息到列表
        messages.append({"role": "user", "content": user_content})
        
        # ===== 调用API =====
        try:
            # 调用OpenAI兼容的API
            response = self.client.chat.completions.create(
                model=self.model,        # 使用的模型
                messages=messages,       # 消息列表
                max_tokens=1000          # 最大返回token数
            )
            
            # 提取并返回翻译结果
            return response.choices[0].message.content
            
        except Exception as e:
            # 返回错误信息
            return f"API Error: {str(e)}"
    
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
            debug_info.append(f"Content: {response.choices[0].message.content}")
            
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
