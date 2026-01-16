# BubbleTrans（Scrappy Comic Translator）v1.0 初始化项目文档

## 1. 项目简介

BubbleTrans 是一个基于 Python + PyQt6 的桌面端美漫翻译辅助工具，面向“看图框选气泡 -> OCR -> 调用大模型翻译”的高频工作流。

核心设计目标：

- 兼容纯文本 LLM：即使模型不支持 Vision，也能通过本地 OCR 完成翻译链路。
- Vision 可选增强：在支持图片输入的模型上，可直接把框选截图发给 LLM，提高理解与翻译质量。
- 轻量交互：像截图工具一样操作，尽量少打断阅读节奏。

## 2. v1.0 已实现功能清单

### 2.1 图片浏览与选区

- 打开漫画图片文件夹（支持常见图片格式：`.jpg/.jpeg/.png/.webp/.bmp`）。
- 左侧列表切换图片；中间画布预览当前图片。
- 鼠标滚轮缩放；右键拖拽平移。
- 左键拖拽框选区域（对话气泡/文本块），弹出确认对话框预览截图。

### 2.2 OCR（本地离线）

- 默认使用 PaddleOCR（英文模型、CPU 模式）对框选区域做文字识别。
- 识别结果输出到右侧 “OCR Text（Editable）” 文本框，可手动修正。
- 识别不到文字时给出提示（建议重新框选或启用 Vision）。

### 2.3 LLM 翻译（OpenAI SDK 兼容接口）

- 通过 OpenAI Python SDK 调用兼容接口（如 OpenRouter / DeepSeek / OpenAI 等）。
- 支持配置：
  - API Key
  - Base URL（如 `https://openrouter.ai/api/v1`）
  - Model Name（如 `google/gemini-2.0-flash-001`）
- 内置“Test Connection”按钮，用最小请求校验网络与配置是否可用。

### 2.4 Vision 模式（可选）

- Settings 中勾选 “Enable Vision (Send Image to LLM)”：
  - 跳过本地 OCR
  - 直接将框选截图作为图片输入发送给 LLM，让模型自行读取英文并翻译成简体中文
- 适用于：字体艺术化、背景复杂、OCR 误差大、或希望模型结合画面语境翻译的场景。

### 2.5 自动上下文（Context）

- 当前版本不再内置“打开文件夹自动联网检索背景”的功能；翻译质量主要依赖于模型选择与提示词约束（例如强调 DC/Marvel 专有名词正确译名与避免直译）。

## 3. 环境要求

### 3.1 运行环境

- Python：3.10+
- 操作系统：Windows（当前仓库提供 `run.bat`）；理论上可在 macOS/Linux 运行（需自行用命令启动）

### 3.2 依赖（requirements.txt）

- PyQt6
- paddlepaddle
- paddleocr
- openai（OpenAI Python SDK）
- Pillow
- requests

## 4. 安装与启动

### 4.1 安装依赖

推荐使用虚拟环境：

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

说明：

- `paddlepaddle/paddleocr` 在部分 Windows 环境可能需要额外构建工具；通常情况下 pip 会安装到可用的 wheel。

### 4.2 启动方式

Windows：

- 双击 `run.bat`（会先执行环境检查，再启动 GUI）。

命令行启动（通用）：

```bash
python src/main.py
```

## 5. 首次使用（推荐流程）

1. 启动应用后点击工具栏 **Settings**。
2. 填写 API Key、Base URL、Model Name。
3. 点击 **Test Connection**，确保网络与模型可用。
4. 点击 **Open Folder**，选择包含漫画图片的文件夹。
5. 在左侧列表中选择图片。
6. 左键拖拽框选一个气泡区域，确认截图后等待处理完成。
7. 右侧上方是 OCR 原文（可编辑），下方是译文结果。

## 6. 配置说明

### 6.1 配置文件位置与读写规则

项目使用根目录下的 `config.json` 保存配置（运行目录为项目根目录时生效）。程序启动时会自动读取该文件并加载配置。

注意：

- `config.json` 包含敏感信息（API Key），不要提交到任何公共仓库。
- 示例参考 `config.example.json`（仅用于展示结构）。

### 6.2 config.json 字段说明

示例（请替换为你自己的值）：

```json
{
  "api_key": "YOUR_API_KEY",
  "base_url": "https://openrouter.ai/api/v1",
  "model": "google/gemini-2.0-flash-001",
  "use_vision": false,
  "successful_models": ["google/gemini-2.0-flash-001"]
}
```

字段含义：

- `api_key`：LLM 平台的密钥。
- `base_url`：兼容 OpenAI SDK 的接口地址（会自动去掉末尾 `/`）。
- `model`：模型名称（由平台定义，例如 OpenRouter 常用 `provider/model` 形式）。
- `use_vision`：是否启用 Vision 模式。
- `successful_models`：曾测试成功的模型列表（用于 Settings 的下拉历史记录）。

### 6.3 Settings 面板与行为说明

- API Key：输入后会以密码形式显示。
- Base URL：默认 `https://openrouter.ai/api/v1`。
- Model Name：可输入或从历史成功记录中选择。
- Enable Vision：勾选后将“跳过本地 OCR”，直接发送图片给模型（需模型支持图片输入）。
- Test Connection：
  - 成功：会把当前 model 写入 `successful_models`，并提示 Connection Verified
  - 失败：会弹出包含详细调试信息的对话框（包含目标 URL、代理信息、错误堆栈、以及 PowerShell 可用的 curl.exe 命令建议）

## 7. 工作模式说明

### 7.1 文本模式（默认）

链路：

1. 框选区域截图
2. PaddleOCR（本地）识别英文
3. 将识别文本 + 背景上下文发送给 LLM 翻译

适用：

- 纯文本模型（不支持图片）
- 网络不稳定但 OCR 仍可离线工作（仅翻译阶段联网）

### 7.2 Vision 模式（可选）

链路：

1. 框选区域截图
2. 直接把图片发送给 LLM，让模型读取英文并翻译

适用：

- 支持图片输入的模型（例如 GPT-4o / Gemini / Claude 等平台的 Vision 模型）
- OCR 难以识别的气泡（艺术字、模糊、扭曲、背景复杂）

## 8. 操作说明（快捷交互）

- 左键拖拽：框选区域
- 右键拖拽：平移画布
- 鼠标滚轮：缩放画布
- 工具栏：
  - Open Folder：选择漫画图片目录
  - Settings：配置 LLM 参数、测试连通性、启用/关闭 Vision
  - 预热 OCR：手动初始化 PaddleOCR（减少首次识别等待）

## 9. 项目结构（v1.0 实际代码）

```text
BubbleTrans/
├── src/
│   ├── main.py                 # 程序入口（启动 MainWindow）
│   ├── ui/
│   │   ├── window.py           # 主窗口、线程任务、截图确认对话框
│   │   ├── canvas.py           # 画布：缩放/平移/框选并输出裁剪 QPixmap
│   │   └── settings.py         # Settings 对话框：配置保存与连通性测试
│   ├── engine/
│   │   ├── ocr.py              # PaddleOCR 初始化与识别封装（含兜底策略）
│   │   ├── llm.py              # OpenAI SDK 客户端封装：翻译与测试
│   │   └── context.py          # DuckDuckGo 搜索：为翻译提供背景上下文
│   └── utils/
│       └── config.py           # config.json 读取与保存
├── config.example.json         # 配置结构示例（请勿放真实密钥）
├── config.json                 # 用户本地配置（敏感）
├── requirements.txt            # Python 依赖
├── setup_check.py              # 启动前依赖检查（可交互安装缺失包）
└── run.bat                     # Windows 一键启动脚本
```

## 10. 常见问题与排障

### 10.1 启动时报依赖缺失

现象：

- 双击 `run.bat` 后提示某些包缺失。

处理：

- 按提示选择安装缺失依赖，或手动执行：

```bash
pip install -r requirements.txt
```

### 10.2 OCR 预热/识别失败

可能原因：

- `paddlepaddle/paddleocr` 安装失败或版本不兼容
- 首次加载模型需要时间或网络（视 PaddleOCR 组件安装情况而定）

建议：

- 先点击工具栏 “预热 OCR”，等待状态栏提示完成。
- 框选更大、更清晰的区域（尽量包含完整文本）。

### 10.3 “未检测到文字”

建议：

- 重新框选：把气泡边缘留一点空白，避免只选到一两行。
- 在 Settings 启用 Vision（前提是模型支持图片输入）。

### 10.4 Test Connection 失败 / 翻译报 API Error

建议排查顺序：

- API Key 是否正确、是否有额度
- Base URL 是否正确（是否带了多余路径、末尾多余 `/`）
- Model Name 是否存在且你有权限调用
- 网络/代理：Settings 的失败弹窗里会显示 HTTP_PROXY/HTTPS_PROXY
- 使用失败弹窗提供的 PowerShell `curl.exe` 命令手动验证连通性

## 11. 安全建议（必须遵守）

- 不要把真实 API Key 写进示例文件或提交到 Git。
- 如果密钥已泄露：立刻在平台上撤销/更换，并清理仓库历史记录（若曾提交）。
