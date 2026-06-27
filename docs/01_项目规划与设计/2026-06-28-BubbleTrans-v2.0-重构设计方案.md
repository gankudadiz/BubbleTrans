# BubbleTrans v2.0 重构设计方案

**日期**: 2026-06-28
**版本**: v2.0
**状态**: 设计已确认，待实施

---

## 1. 重构动机

经过半年发展，多模态大模型能力大幅提升，v1.0 时代「本地 OCR + LLM 翻译」的两段式架构已过时。本次重构核心思路：

> **放弃本地 OCR，纯靠多模态大模型完成识别+翻译。**

收益：
- 消除 PaddleOCR 及其大型依赖（paddlepaddle ~500MB），部署成本归零
- 提示词统一，LLM 同时输出原文+译文，架构极简
- 支持任意语言，不再受 PaddleOCR 语种模型限制

---

## 2. 需求清单

| # | 需求 | 说明 |
|---|------|------|
| R1 | 纯多模态 OCR | 删除 `paddleocr`、`paddlepaddle`、`requests`；所有文字识别由多模态 LLM 完成 |
| R2 | 双协议 API 支持 | 支持 OpenAI `/v1/chat/completions` 和 Anthropic `/v1/messages` 两种协议 |
| R3 | 全页翻译模式 | 默认模式：点击按钮 → 发送整张图片给 LLM → 返回原文段落 + 译文段落 |
| R4 | 框选翻译保留 | 鼠标拖框选择区域 → 裁剪 → 发送 → 翻译 |
| R5 | 段落式原文+译文展示 | 右侧面板分上下两区，原文段落间空行分隔，译文一一对应 |
| R6 | 目标语言变量 | Settings 中设置目标语言（默认中文），注入提示词 `{target_lang}` 变量 |
| R7 | 依赖精简 | requirements.txt 只保留 PyQt6、openai、Pillow |

---

## 3. 架构决策

### 3.1 双协议实现策略

**决策：只用 OpenAI SDK，不引入 Anthropic SDK。**

理由：
- 目标用户使用中转站（one-api / new-api 等），中转站对外统一暴露 OpenAI 兼容的 `/v1/chat/completions` 端点
- 协议转换由中转站完成，客户端无需感知后端实际模型是 GPT 还是 Claude
- 一套代码，零协议适配成本

实现：保持现有 `openai` 包，用户填入中转站的 `base_url` + `api_key` + `model` 即可。

### 3.2 OCR 引擎删除

`src/engine/ocr.py` 整个文件删除。所有需要文字识别的场景改为直接把图片作为 `image_url` content part 发给 LLM。

### 3.3 提示词设计

采用结构化输出，一条 prompt 同时产出原文和译文：

```markdown
## System Prompt

你是一个专业的漫画翻译助手。你的任务是：
1. 识别图片中所有文字，按阅读顺序整理成段落
2. 将原文翻译成{target_lang}

输出格式严格要求如下（不要添加任何额外说明）：

<原文>
段落一的内容…
段落二的内容…
</原文>

<{language_tag}>
段落一的翻译…
段落二的翻译…
</{language_tag}>

注意：
- 每个段落之间用空行分隔
- 原文和译文段落数量必须一一对应
- 气泡内的拟声词（如"BAM""BOOM"）保留原样不翻译
- 专有名词（人名、地名）保留原文
- 不确定的内容保留原文并标注[?]
```

变量说明：

| 变量 | 示例值 | 来源 |
|------|--------|------|
| `{target_lang}` | `简体中文` | `config.json` → `target_lang` 字段 |
| `{language_tag}` | `中文` | 由 `target_lang` 映射（内置映射表） |

语言 → 标签映射：

| target_lang | language_tag |
|-------------|-------------|
| 简体中文 | 中文 |
| 日本語 | 日本語 |
| 한국어 | 한국어 |
| English | English |
| Français | Français |

### 3.4 解析逻辑

LLM 返回后，解析 `<原文>...</原文>` 和 `<{language_tag}>...</{language_tag}>` 区段：
- 按 `\n\n` 分割段落
- 原文段落填入上方 QTextEdit（只读），段落间保留空行
- 译文段落填入下方 QTextEdit（只读），段落间保留空行

---

## 4. UI 重新设计

### 4.1 整体布局（不变）

```
┌──────────┬──────────────────┬────────────────┐
│ 文件列表  │     画布         │   翻译面板      │
│ (200px)  │   (可伸缩)       │   (300px)      │
└──────────┴──────────────────┴────────────────┘
```

### 4.2 右侧翻译面板（重构）

```
┌──────────────────────────────────────┐
│ [翻译当前页]          语言: 中文     │  ← 工具栏
├──────────────────────────────────────┤
│ ▼ 原文                               │
│ ┌──────────────────────────────────┐ │
│ │ (段落格式, 只读, 段落间有空行)    │ │
│ │                                  │ │
│ └──────────────────────────────────┘ │
│ ▼ 译文（中文）                       │
│ ┌──────────────────────────────────┐ │
│ │ (段落格式, 只读, 段落间有空行)    │ │
│ │                                  │ │
│ └──────────────────────────────────┘ │
└──────────────────────────────────────┘
```

要点：
- 两个 QTextEdit 均为只读，支持滚动
- 段落间以空行分隔（LLM 输出 + 解析逻辑保证）
- 框选翻译结果也填入同一面板，此时标签前缀改为"框选"
- 移除现有的 OCR 文本编辑框（v1.0 残留）

### 4.3 Settings 对话框新增字段

在现有 Settings 对话框中新增：

```
┌──────────────────────────────────────┐
│ API Key:     [••••••••••••••••••••]  │
│ Base URL:    [https://...         ]  │
│ Model:       [gemini-2.5-flash  ▾]  │
│ Vision:      [✓] (始终启用)          │
│ 目标语言:    [简体中文         ▾]    │  ← 新增
│                                      │
│ [Test Connection]   [OK] [Cancel]    │
└──────────────────────────────────────┘
```

目标语言选项：简体中文、日本語、한국어、English、Français（可后续扩展）。

---

## 5. 配置文件变更

`config.json` 新增字段：

```json
{
  "api_key": "sk-xxx",
  "base_url": "https://your-proxy.com/v1",
  "model": "gemini-2.5-flash",
  "use_vision": true,
  "target_lang": "简体中文",
  "successful_models": []
}
```

- `use_vision` 默认改为 `true`（v1.0 默认 `false`）
- 新增 `target_lang`，默认 `"简体中文"`
- `config.example.json` 同步更新

---

## 6. 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 🗑️ 删除 | `src/engine/ocr.py` | 整个文件删除 |
| ✏️ 重写 | `src/engine/llm.py` | 新提示词系统 + 结构化输出解析 |
| ✏️ 修改 | `src/engine/__init__.py` | 移除 ocr 相关导入（如有） |
| ✏️ 重构 | `src/ui/window.py` | 右侧面板改为双区段落显示 + 全页翻译按钮；移除 OcrInitWorker；TranslationWorker 去掉 OCR 分支 |
| ✏️ 修改 | `src/ui/settings.py` | 新增目标语言下拉框；Vision 改为始终启用 |
| ✏️ 修改 | `src/utils/config.py` | 新增 `target_lang` 字段 |
| — 不变 | `src/main.py` | |
| — 不变 | `src/ui/canvas.py` | 框选逻辑保留 |
| ✏️ 精简 | `requirements.txt` | 移除 paddlepaddle、paddleocr、requests |
| ✏️ 修改 | `setup_check.py` | 移除 PaddleOCR 相关检查 |
| ✏️ 修改 | `config.example.json` | 新增 `target_lang` 字段 |
| — 不变 | `run.bat` | |

---

## 7. 工作线程简化

v1.0 的 `TranslationWorker.run()` 逻辑：

```python
# v1.0: 两段式
if use_vision:
    result = llm.translate("", ctx, path, True)  # 跳过OCR直接发图
else:
    ocr_text = ocr.recognize(path)               # 先OCR
    result = llm.translate(ocr_text, ctx, path)  # 再翻译
```

v2.0 简化为：

```python
# v2.0: 纯多模态
result = llm.translate_image(image_path, target_lang)
# translate_image 内部: 构建 system prompt → 发送图片 → 解析 <原文>/<译文> → 返回 (origin_text, translation)
```

不再需要 `ocr_engine`、`OcrInitWorker`、OCR 预热逻辑。

---

## 8. 验收标准

- [ ] 启动程序，不再要求安装 PaddleOCR
- [ ] `requirements.txt` 只剩 3 个包
- [ ] 打开图片，点击「翻译当前页」，右侧原文/译文正确显示，段落间有空行
- [ ] 鼠标拖框选择区域，翻译结果正确
- [ ] Settings 中可以切换目标语言（中文→日文），提示词变量正确注入
- [ ] 切换到非中文语言后，翻译标签和输出正确
- [ ] 删除 `src/engine/ocr.py` 后程序不报错
- [ ] `config.json` 正确读写 `target_lang` 字段
