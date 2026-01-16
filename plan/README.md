# BubbleTrans (Scrappy Comic Translator) 开发计划

这是一个基于 Python 和 PyQt6 开发的轻量级美漫翻译辅助工具。本项目旨在兼容所有类型的 LLM（包括不支持视觉的纯文本模型如 DeepSeek），因此内置了本地 OCR 引擎作为核心组件，确保在任何网络/模型条件下均可运行。

## 1. 项目核心理念

* **兼容性优先**: 必须支持纯文本大模型（DeepSeek, GPT-3.5 等）。因此 **本地 OCR** 是必选环节。
* **双模驱动**:
  * **文本模式 (通用)**: 本地 OCR 提取文本 -> 发送给 LLM 翻译。
  * **视觉增强模式 (可选)**: 本地 OCR 提取文本 + 原始图片 -> 发送给支持视觉的 LLM (如 GPT-4o, Gemini) 以获得更好的语境理解。
* **轻量高效**: 界面简洁，操作逻辑类似“截图工具”，即用即走。

## 2. 技术栈选择

* **编程语言**: Python 3.10+
* **GUI 框架**: PyQt6
  * 用于构建跨平台桌面应用，提供流畅的图片浏览和截图选区体验。
* **OCR 引擎 (核心)**: **PaddleOCR** (轻量级英语模型)
  * *理由*: 相比 Tesseract，PaddleOCR 对复杂背景和艺术字体的识别率更高，且提供轻量级 CPU 模型（~10MB），无需 GPU 即可流畅运行。
* **API 客户端**: OpenAI Python SDK
  * 兼容 OpenRouter、DeepSeek 官方 API 等。
* **网络搜索**: `duckduckgo-search`
  * 用于自动搜索漫画背景信息。

## 3. 功能模块设计

### 3.1 用户界面 (UI)

* **主窗口**:
  * **资源栏 (左)**: 简单的文件树，快速切换图片。
  * **画布 (中)**: 图片预览区，支持滚轮缩放、右键平移。
  * **翻译栏 (右)**:
    * **上部**: 显示 OCR 识别到的原文（支持用户手动修正）。
    * **下部**: 显示 LLM 返回的译文。
* **状态栏**: 显示当前使用的 OCR 引擎状态、LLM 连接状态、漫画背景关键词。

### 3.2 核心工作流

1. **导入与背景获取**:
   * 用户打开文件夹。
   * 系统提取文件夹名（如 "Batman No.1"），后台调用 `duckduckgo-search` 获取简介（如 "Batman origin story..."）。

2. **选区与识别 (OCR)**:
   * 用户在画布上框选对话气泡。
   * **Local OCR**: 调用 PaddleOCR 识别框选区域的文字。
   * **结果展示**: 识别出的英文原文自动填入“翻译栏”上部，供用户检查（防止 OCR 错误）。

3. **大模型翻译 (LLM)**:
   * **Prompt 构建**:
     * `System`: "你是一个翻译助手。背景信息: {context}。"
     * `User`: "翻译这段文字: {ocr_text}"
   * **视觉增强 (如果配置了 Vision 模型)**:
     * 将框选的截图 Base64 附加到请求中，提示模型：“参考这张图片的情境来翻译文字”。
   * **结果返回**: 译文显示在“翻译栏”下部。

### 3.3 配置管理

* **OCR 设置**: 语言选择（默认 English），识别置信度阈值。
* **LLM 设置**:
  * API Base URL (OpenRouter/DeepSeek/OpenAI)
  * API Key
  * Model Name
  * **Vision Support**: 复选框 [ ] 启用视觉能力 (若选中，会同时发送图片)。

## 4. 开发计划 (Roadmap)

### Phase 1: 基础架构与 OCR
* [ ] 搭建 PyQt6 主界面框架。
* [ ] 集成 PaddleOCR (CPU版)，实现基础的图片文字识别功能。
* [ ] 实现图片加载、缩放、框选交互。

### Phase 2: LLM 对接
* [ ] 实现 OpenAI SDK 的通用调用接口。
* [ ] 完成“OCR 文本 -> LLM -> 界面显示”的完整链路。
* [ ] 添加 API 配置面板。

### Phase 3: 体验优化
* [ ] 实现文件夹扫描与自动背景搜索 (Context Agent)。
* [ ] 优化 Prompt 模板，专门针对美漫风格（全大写、俚语）。
* [ ] 打包发布 (PyInstaller)。

## 5. 目录结构

```text
/BubbleTrans
├── src/
│   ├── main.py           # 入口
│   ├── ui/               # 界面
│   │   ├── window.py
│   │   ├── canvas.py     # 截图选区核心
│   │   └── panel.py      # 文本显示面板
│   ├── engine/           # 核心引擎
│   │   ├── ocr.py        # PaddleOCR 封装
│   │   ├── llm.py        # API 调用
│   │   └── search.py     # 背景搜索
│   └── utils/
├── config.json           # 用户配置
├── requirements.txt
└── plan/
    └── README.md         # 详细计划文档
```
