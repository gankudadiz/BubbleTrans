#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - 设置对话框模块

本模块实现了应用程序的设置界面，用于配置LLM API的相关参数。

主要功能：
1. API密钥配置 - 输入API密钥
2. 服务器地址配置 - 设置API服务器地址
3. 模型选择 - 选择使用的LLM模型
4. Vision模式开关 - 启用/禁用图片识别功能
5. 连接测试 - 测试API配置是否正确
6. 模型历史记录 - 记住成功使用的模型

支持的API服务：
- OpenRouter（默认）
- OpenAI官方API
- 兼容OpenAI API格式的其他服务
"""

# ============================================================================
# PyQt6 框架导入
# ============================================================================
from PyQt6.QtWidgets import (
    QDialog,           # 对话框基类
    QVBoxLayout,       # 垂直布局
    QHBoxLayout,       # 水平布局
    QFormLayout,       # 表单布局（标签-输入框对）
    QLineEdit,         # 单行文本输入框
    QDialogButtonBox,  # 按钮盒（确定/取消等）
    QCheckBox,         # 复选框
    QLabel,            # 标签
    QMessageBox,       # 消息对话框
    QPushButton,       # 按钮
    QInputDialog,      # 输入对话框（新建档案命名）
    QApplication,      # 应用程序对象
    QTextEdit,         # 多行文本编辑框
    QComboBox          # 下拉选择框
)

# ============================================================================
# 项目内部模块导入
# ============================================================================
from engine.llm import llm_engine  # LLM引擎实例
from utils.config import save_config, load_config  # 配置保存/加载函数


# ============================================================================
# DebugDialog 类 - 调试信息对话框
# ============================================================================
# 用于显示详细的连接测试失败信息
# 当API连接失败时，展示所有调试信息帮助用户排查问题
# ============================================================================
class DebugDialog(QDialog):
    """
    调试信息对话框
    
    显示详细的错误信息和调试数据，用于排查API连接问题
    
    功能：
    - 显示错误标题和信息
    - 显示完整的调试日志
    - 只读文本编辑框
    - 关闭按钮
    """
    
    def __init__(self, title, message, parent=None):
        """
        初始化调试对话框
        
        参数:
            title: 对话框标题
            message: 要显示的调试信息
            parent: 父窗口
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(600, 400)  # 设置对话框大小
        
        # 创建垂直布局
        layout = QVBoxLayout(self)
        
        # 创建只读文本编辑框
        text_edit = QTextEdit()
        text_edit.setPlainText(message)
        text_edit.setReadOnly(True)
        layout.addWidget(text_edit)
        
        # 添加关闭按钮
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


# ============================================================================
# SettingsDialog 类 - 设置对话框
# ============================================================================
# 应用程序的设置界面，用于配置LLM API
#
# 布局结构：
# ┌─────────────────────────────────────┐
# │ Settings                          │
# ├─────────────────────────────────────┤
# │ API Key:     [****************]     │
# │ Base URL:    [https://...]      │
# │ Model Name:  [google/...     ▼]   │
# │             [x] Enable Vision      │
# │                                     │
# │ Note: ...                          │
# │          [Test Connection]         │
# │                [OK] [Cancel]        │
# └─────────────────────────────────────┘
# ============================================================================
class SettingsDialog(QDialog):
    """
    设置对话框 - 配置LLM API参数
    
    功能：
    - 输入和保存API密钥
    - 设置API服务器地址
    - 选择或输入模型名称
    - 启用/禁用Vision模式
    - 测试连接
    - 记录成功使用的模型
    
    使用流程：
    1. 打开设置对话框
    2. 填写API密钥、地址、模型
    3. 可选：点击"Test Connection"测试
    4. 点击"OK"保存设置
    """
    
    def __init__(self, parent=None):
        """
        初始化设置对话框
        
        参数:
            parent: 父窗口
        """
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(520, 420)
        self.init_ui()
    
    # ===================== 模型历史记录管理 =====================
    
    def _load_successful_models(self):
        """
        加载成功使用的模型列表
        
        从配置文件中读取之前成功连接的模型列表
        
        返回:
            list: 模型名称列表，按使用频率排序
        """
        config = load_config()
        models = config.get("successful_models", [])
        
        if not isinstance(models, list):
            return []
        
        # 去重和清理
        cleaned = []
        seen = set()
        for item in models:
            if not isinstance(item, str):
                continue
            value = item.strip()
            if not value or value in seen:
                continue
            seen.add(value)
            cleaned.append(value)
        
        return cleaned
    
    def _save_successful_model(self, model: str):
        """
        保存成功的模型到历史记录
        
        将成功连接的模型添加到历史列表顶部
        
        参数:
            model: 模型名称
        """
        model = (model or "").strip()
        if not model:
            return
        
        models = self._load_successful_models()
        
        # 移除已存在的同名模型（稍后添加到顶部）
        models = [m for m in models if m != model]
        
        # 添加到顶部
        models.insert(0, model)
        
        # 只保留最近的30个
        models = models[:30]
        
        # 保存到配置
        save_config({"successful_models": models})
        
        # 更新下拉框
        if hasattr(self, "model_combo") and self.model_combo is not None:
            existing = set(self.model_combo.itemText(i) for i in range(self.model_combo.count()))
            if model not in existing:
                self.model_combo.insertItem(0, model)
            self.model_combo.setCurrentText(model)
    
    # ===================== UI初始化 =====================
    
    def init_ui(self):
        """
        初始化用户界面
        
        创建所有UI组件：
        - 表单布局（API Key、Base URL、Model）
        - Vision模式复选框
        - 提示信息
        - 测试按钮
        - 确定/取消按钮
        """
        # 主布局
        layout = QVBoxLayout(self)
        
        # ===== 配置档案选择器 =====
        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("配置档案:"))
        self.profile_combo = QComboBox()
        self.profile_combo.currentTextChanged.connect(self._on_profile_changed)
        profile_row.addWidget(self.profile_combo, 1)
        
        self.btn_new_profile = QPushButton("新建")
        self.btn_new_profile.clicked.connect(self._new_profile)
        profile_row.addWidget(self.btn_new_profile)
        
        self.btn_del_profile = QPushButton("删除")
        self.btn_del_profile.clicked.connect(self._delete_profile)
        profile_row.addWidget(self.btn_del_profile)
        layout.addLayout(profile_row)
        
        # ===== 表单布局（标签-输入框对） =====
        form = QFormLayout()
        
        self._refresh_profile_list()  # 填充档案列表
        
        # ===== API密钥输入框 =====
        self.api_key_edit = QLineEdit(llm_engine.api_key)
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        # 密码模式显示为圆点，保护API密钥
        
        # ===== Base URL输入框 =====
        self.base_url_edit = QLineEdit(llm_engine.base_url)
        self.base_url_edit.setPlaceholderText("https://openrouter.ai/api/v1")
        
        # ===== 模型选择下拉框 =====
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)  # 允许用户输入自定义模型
        
        # 加载历史记录
        successful_models = self._load_successful_models()
        if successful_models:
            self.model_combo.addItems(successful_models)
        
        # 设置当前模型
        self.model_combo.setCurrentText(llm_engine.model)
        if self.model_combo.lineEdit():
            self.model_combo.lineEdit().setPlaceholderText("google/gemini-2.0-flash-001")
        
        # ===== Vision模式复选框 =====
        self.vision_check = QCheckBox("Enable Vision (Send Image to LLM)")
        self.vision_check.setChecked(True)   # 始终勾选
        self.vision_check.setEnabled(False)  # 禁用，不可取消
        self.vision_check.setToolTip("v2.0 纯多模态架构，Vision 始终启用")
        
        # ===== 添加到表单 =====
        form.addRow("API Key:", self.api_key_edit)
        form.addRow("Base URL:", self.base_url_edit)
        form.addRow("Model Name:", self.model_combo)
        form.addRow("", self.vision_check)  # 空标签，复选框单独一行
        
        # ===== 目标语言下拉框 =====
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["简体中文", "繁體中文", "日本語", "한국어", "English", "Français"])
        # 从引擎读取当前语言
        current_lang = getattr(llm_engine, 'target_lang', '简体中文')
        idx = self.lang_combo.findText(current_lang)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        form.addRow("目标语言:", self.lang_combo)
        
        # ===== 预翻译设置 =====
        self.prefetch_check = QCheckBox("翻页时自动预翻译")
        config = load_config()
        self.prefetch_check.setChecked(config.get("prefetch_enabled", False))
        form.addRow("", self.prefetch_check)

        self.prefetch_count_combo = QComboBox()
        self.prefetch_count_combo.addItems(["1", "3", "5"])
        self.prefetch_count_combo.setCurrentText(str(config.get("prefetch_count", 3)))
        form.addRow("预翻译页数:", self.prefetch_count_combo)

        self.prefetch_concurrent_combo = QComboBox()
        self.prefetch_concurrent_combo.addItems(["1", "2", "3"])
        self.prefetch_concurrent_combo.setCurrentText(str(config.get("prefetch_concurrent", 2)))
        form.addRow("并发数:", self.prefetch_concurrent_combo)
        
        layout.addLayout(form)
        
        # ===== 提示信息 =====
        hint = QLabel("v2.0 纯多模态架构，所有翻译均通过图片+LLM完成")
        hint.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(hint)
        
        # ===== 测试按钮 =====
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self.test_connection)
        layout.addWidget(self.test_btn)
        
        # ===== 确定/取消按钮 =====
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save_settings)  # 确定：保存设置
        buttons.rejected.connect(self.reject)         # 取消：关闭对话框
        layout.addWidget(buttons)
    
    # ===================== 功能方法 =====================
    
    def _refresh_profile_list(self):
        """刷新档案下拉列表"""
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        profiles = llm_engine.get_profiles()
        for name in sorted(profiles.keys()):
            self.profile_combo.addItem(name)
        # 选中当前激活的档案
        idx = self.profile_combo.findText(llm_engine.active_profile)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)
        self.profile_combo.blockSignals(False)
        # 至少保留一个档案，最后一个不可删除
        self.btn_del_profile.setEnabled(len(profiles) > 1)
    
    def _on_profile_changed(self, name):
        """切换档案时回填对应配置"""
        if not name:
            return
        profiles = llm_engine.get_profiles()
        profile = profiles.get(name, {})
        self.api_key_edit.setText(profile.get("api_key", ""))
        self.base_url_edit.setText(profile.get("base_url", ""))
        self.model_combo.setCurrentText(profile.get("model", ""))
    
    def _new_profile(self):
        """新建配置档案"""
        name, ok = QInputDialog.getText(self, "新建档案", "档案名称:")
        if not ok or not name.strip():
            return
        name = name.strip()
        # 保存当前输入的配置为新档案
        llm_engine.save_profile(
            name,
            self.api_key_edit.text().strip(),
            self.base_url_edit.text().strip(),
            self.model_combo.currentText().strip()
        )
        # 切换到新档案
        llm_engine.switch_profile(name)
        self._refresh_profile_list()
    
    def _delete_profile(self):
        """删除当前档案"""
        name = self.profile_combo.currentText()
        if not name:
            return
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除配置档案「{name}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        llm_engine.delete_profile(name)
        self._refresh_profile_list()
        # 重新加载当前档案
        self._on_profile_changed(self.profile_combo.currentText())
    
    def test_connection(self):
        """
        测试API连接
        
        调用LLM引擎的测试功能，验证API配置是否正确
        
        测试流程：
        1. 获取输入的API参数
        2. 禁用测试按钮，防止重复点击
        3. 调用llm_engine.test_connection()
        4. 成功：保存模型到历史记录，显示成功消息
        5. 失败：显示详细的调试信息对话框
        """
        # 获取输入
        api_key = self.api_key_edit.text().strip()
        base_url = self.base_url_edit.text().strip()
        model = self.model_combo.currentText().strip()
        
        # 验证输入
        if not api_key:
            QMessageBox.warning(self, "Warning", "Please enter API Key first.")
            return
        
        # 禁用按钮并更新文本
        self.test_btn.setEnabled(False)
        self.test_btn.setText("Testing...")
        
        # 强制刷新UI
        QApplication.processEvents()
        
        # 执行测试
        success, message = llm_engine.test_connection(api_key, base_url, model)
        
        # 恢复按钮状态
        self.test_btn.setEnabled(True)
        self.test_btn.setText("Test Connection")
        
        # 处理结果
        if success:
            # 成功：保存模型到历史
            self._save_successful_model(model)
            QMessageBox.information(self, "Success", "Connection Verified!")
        else:
            # 失败：显示调试信息
            dlg = DebugDialog("Connection Failed - Debug Info", message, self)
            dlg.exec()
    
    def save_settings(self):
        """
        保存设置
        
        获取输入框中的值，配置LLM引擎并保存到配置文件
        """
        api_key = self.api_key_edit.text().strip()
        
        # 验证API密钥
        if not api_key:
            QMessageBox.warning(self, "Warning", "API Key is empty!")
            return
        
        profile_name = self.profile_combo.currentText().strip()
        base_url = self.base_url_edit.text().strip()
        model = self.model_combo.currentText().strip()
        
        # 配置LLM引擎
        llm_engine.configure(api_key=api_key, base_url=base_url, model=model)
        llm_engine.target_lang = self.lang_combo.currentText().strip()
        llm_engine.use_vision = True
        
        # 保存到当前档案
        llm_engine.save_profile(profile_name, api_key, base_url, model)
        # 如果切换了档案，同步激活
        if profile_name != llm_engine.active_profile:
            llm_engine.switch_profile(profile_name)
        # 保存通用设置
        save_config({
            "target_lang": llm_engine.target_lang,
            "use_vision": True,
            "prefetch_enabled": self.prefetch_check.isChecked(),
            "prefetch_count": int(self.prefetch_count_combo.currentText()),
            "prefetch_concurrent": int(self.prefetch_concurrent_combo.currentText()),
        })
        
        # 关闭对话框
        self.accept()
