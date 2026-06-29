# BubbleTrans v2.1

漫画气泡翻译器，基于多模态大模型。识别 + 翻译 + 剧情总结，一次搞定。

A comic speech-bubble translator powered by multimodal LLMs — OCR, translation, and page summary in one go.

---

## 截图 / Screenshot

![Main UI](file/翻译主界面_v2.1.png)

*翻译主界面：左侧文件列表 · 中间漫画画布 · 右侧分段切换译文 + 当页AI总结*
*Main UI: file list (left) · canvas (center) · segmented translation + AI summary (right)*

---

## 功能 / Features

### 翻译

- **全页翻译**：点击按钮，LLM 同时识别图片文字并翻译，右侧显示译文
- **框选翻译**：鼠标拖框选择任意气泡区域单独翻译
- **原文/译文分段切换**：共用文本区，一键切换，默认显示译文
- **目标语言切换**：支持简体中文、日本語、한국어、English、Français 等

### AI 增强

- **当页剧情总结**：翻译同时生成 2-4 句剧情摘要，理解画面在讲什么
- **翻译备注**：列出专有名词译法、双关语处理、文化梗解释，翻译决策透明

### 体验

- 左右方向键翻页 · 右键拖拽平移 · 滚轮缩放
- 配置档案：多套 API 配置（不同中转站/模型）一键切换
- 兼容任何 OpenAI 兼容中转站（one-api / new-api / OpenRouter 等）

---

### Translation

- **Full-page**: One click, LLM recognizes + translates all text on the page
- **Area selection**: Drag-select any speech bubble for targeted translation
- **Segmented switch**: Original/translation share one text area, default to translation
- **Target language**: 简体中文, 日本語, 한국어, English, Français, and more

### AI-Powered

- **Page plot summary**: 2-4 sentence recap of what's happening on the page
- **Translation notes**: Name choices, pun handling, cultural references — transparent decisions

### Quality of Life

- Arrow keys to flip pages · right-drag to pan · scroll to zoom
- Multi-profile API management — switch proxies/models with one click
- Works with any OpenAI-compatible API gateway

---

## 快速开始 / Quick Start

1. 安装 **Python 3.10+** / Install Python 3.10+
2. 双击 `run.bat` / Double-click `run.bat`（自动创建虚拟环境、安装依赖、启动程序）
3. Settings → 填入 API Key / Base URL / Model → Test Connection
4. Open Folder → 选择漫画文件夹
5. 选中图片 → 点击「**翻译当前页**」
6. 或左键拖框选择气泡区域翻译
7. 右侧查看译文 + 剧情总结

---

## 依赖 / Dependencies

```
PyQt6>=6.4.0
openai>=1.0.0
Pillow>=9.0.0
```

仅 3 个包。v1.0 时代的 PaddleOCR / paddlepaddle 已完全移除。

Only 3 packages. PaddleOCR / paddlepaddle from v1.0 are completely removed.

---

## 配置 / Configuration

`config.json`（首次运行自动生成）：

```json
{
  "profiles": {
    "默认": {
      "api_key": "sk-xxx",
      "base_url": "https://your-proxy.com",
      "model": "gemini-2.5-flash"
    },
    "opencode": {
      "api_key": "sk-xxx",
      "base_url": "https://opencode.ai/zen/go/v1",
      "model": "mimo-v2.5"
    }
  },
  "active_profile": "opencode",
  "target_lang": "简体中文"
}
```

| 字段 | 说明 |
|------|------|
| `profiles` | 多套 API 配置，Settings 中切换 |
| `active_profile` | 当前激活的配置档案 |
| `target_lang` | 目标翻译语言 |

`config.json` 包含 API Key，已在 `.gitignore` 中排除。

---

## 安全 / Security

- `config.json` excluded from Git via `.gitignore`
- Only commit `config.example.json` when open-sourcing

---

## 关键词 / Keywords

comic translator · speech bubble · manga · multimodal · LLM · Vision · AI summary · PyQt6 · OpenAI · Gemini · OpenRouter

---

## License

MIT. See [LICENSE](LICENSE).
