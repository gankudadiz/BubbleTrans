#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - Scrappy Comic Translator 主程序入口

这个项目是一个漫画翻译工具，用于将英文漫画翻译成中文。
本文件是整个应用程序的入口点，负责初始化PyQt6 GUI框架并启动主窗口。
"""

import sys
import os
import logging
import traceback
from datetime import datetime
from pathlib import Path

# ============================================================================
# 日志系统配置
# ============================================================================
# 在项目根目录创建 logs 目录，所有崩溃和错误信息都会写入日志文件
# 这样即使程序闪退，也能事后追溯原因
# ============================================================================
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
MAX_LOG_FILES = 10   # 最多保留最近10个日志文件，旧的自动清理

def _rotate_logs():
    """轮转清理旧日志文件，只保留最近 MAX_LOG_FILES 个"""
    if not LOG_DIR.exists():
        return
    # 收集所有日志文件，按修改时间排序（旧 → 新）
    log_files = sorted(
        LOG_DIR.glob("bubbletrans_*.log"),
        key=lambda f: f.stat().st_mtime
    )
    # 超出上限的删除
    if len(log_files) > MAX_LOG_FILES:
        for f in log_files[:len(log_files) - MAX_LOG_FILES]:
            try:
                f.unlink()
            except OSError:
                pass

def setup_logging():
    """初始化日志系统，输出到控制台和文件（自动轮转保留最近10个日志）"""
    LOG_DIR.mkdir(exist_ok=True)
    _rotate_logs()
    
    # 根 logger 配置
    logger = logging.getLogger("BubbleTrans")
    logger.setLevel(logging.DEBUG)
    
    # 文件 handler — 每次运行新建日志文件，带时间戳
    log_file = LOG_DIR / f"bubbletrans_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(fh)
    
    # 控制台 handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(ch)
    
    return logger

def setup_exception_hook(logger):
    """
    设置全局未捕获异常钩子
    
    任何未被 try/except 捕获的异常都会通过此函数输出到日志，
    然后显示错误对话框，避免程序静默闪退。
    """
    original_hook = sys.excepthook
    
    def global_exception_handler(exc_type, exc_value, exc_tb):
        # 记录到日志文件
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.critical(f"未捕获的异常:\n{tb_str}")
        
        # 尝试显示 GUI 错误对话框（如果 QApplication 已初始化）
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance()
            if app:
                QMessageBox.critical(
                    None, "程序崩溃",
                    f"发生未处理的异常:\n\n{exc_value}\n\n"
                    f"详细信息已写入日志文件。\n"
                    f"请将 logs 目录下的日志文件发送给开发者。"
                )
        except Exception:
            pass
        
        # 调用原始钩子（打印到 stderr）
        original_hook(exc_type, exc_value, exc_tb)
    
    sys.excepthook = global_exception_handler


_logger = setup_logging()
setup_exception_hook(_logger)

# ============================================================================
# 模块路径配置
# ============================================================================
# 将当前文件所在目录添加到Python的模块搜索路径中
# 这样就可以使用相对导入（如 from ui.window import MainWindow）
# 
# 原理说明：
# - __file__: 当前文件的完整路径
# - os.path.abspath(__file__): 获取绝对路径
# - os.path.dirname(): 获取目录部分
# - sys.path.append(): 将目录添加到搜索路径
# ============================================================================
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ============================================================================
# GUI框架导入
# ============================================================================
# PyQt6是Qt框架的Python绑定版本，用于创建图形用户界面
# QApplication: 管理应用程序的核心对象，处理事件循环和窗口管理
# MainWindow: 自定义的主窗口类（在ui/window.py中定义）
# ============================================================================
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from ui.window import MainWindow
from qt_material import apply_stylesheet


def main():
    """
    主函数 - 应用程序的入口点
    
    这个函数执行以下操作：
    1. 创建QApplication实例 - 这是每个PyQt6应用程序必须的
    2. 创建主窗口实例 - 显示应用程序的UI
    3. 显示窗口
    4. 启动事件循环 - 等待用户交互
    
    参数说明：
        sys.argv: 命令行参数列表，传递给QApplication
                 这样可以通过命令行传递参数给应用程序
    """
    _logger.info("BubbleTrans 启动")
    _logger.info(f"Python: {sys.version}")
    _logger.info(f"工作目录: {os.getcwd()}")
    
    # 创建Qt应用程序实例
    # sys.argv 包含命令行参数，例如：
    # python main.py --fullscreen
    # 这些参数会被Qt框架处理
    app = QApplication(sys.argv)

    # 跟随系统主题自动选择 Material Design 主题
    # Windows: 设置 → 个性化 → 颜色 → 选择模式
    # macOS: 系统设置 → 外观
    scheme = app.styleHints().colorScheme()
    theme = 'dark_teal.xml' if scheme == Qt.ColorScheme.Dark else 'light_teal.xml'
    _logger.info(f"系统主题: {'暗色' if scheme == Qt.ColorScheme.Dark else '亮色'} → 使用 {theme}")

    apply_stylesheet(app, theme=theme, extra={
        'font_family': 'Microsoft YaHei',
        'density_scale': '-1',
    })
    
    # 创建主窗口实例
    # MainWindow 类定义了应用程序的主要UI界面
    window = MainWindow()
    
    # 显示窗口
    # 默认情况下窗口是隐藏的，需要调用show()方法显示
    window.showMaximized()
    
    # 启动应用程序的事件循环
    # exec() 方法开始处理事件，会阻塞程序直到用户关闭窗口
    # sys.exit() 确保程序以正确的退出码结束
    _logger.info("进入事件循环")
    exit_code = app.exec()
    _logger.info(f"事件循环结束，退出码: {exit_code}")
    sys.exit(exit_code)


# ============================================================================
# 程序入口保护
# ============================================================================
# __name__ 是Python内置的变量：
# - 当直接运行这个脚本时，__name__ == "__main__"
# - 当作为模块导入时，__name__ == "模块名"
# 
# 这样设计的好处是：
# 1. 这个文件可以直接运行（python main.py）
# 2. 也可以作为模块被其他程序导入（import main）
# 3. 导入时不会执行main()函数
# ============================================================================
if __name__ == "__main__":
    # 调用主函数启动应用程序
    main()
