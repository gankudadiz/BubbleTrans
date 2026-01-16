#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - 配置文件管理模块

本模块提供了应用程序配置文件的读写功能。

功能说明：
1. 加载配置 - 从config.json读取配置到字典
2. 保存配置 - 将配置字典更新到config.json
3. 错误处理 - 文件不存在或格式错误时返回空字典

配置文件格式（config.json）：
{
    "api_key": "your-api-key",
    "base_url": "https://openrouter.ai/api/v1",
    "model": "google/gemini-2.0-flash-001",
    "use_vision": false,
    "successful_models": ["google/gemini-2.0-flash-001"]
}

注意事项：
- 配置文件位于项目根目录
- 编码使用UTF-8
- 使用JSON格式存储
- 保存时使用4空格缩进，便于阅读
"""

# ============================================================================
# 标准库导入
# ============================================================================
import json           # JSON格式处理
import os             # 文件系统操作

# ============================================================================
# 配置常量
# ============================================================================
# 配置文件名，相对于项目根目录
CONFIG_FILE = "config.json"


# ============================================================================
# 加载配置
# ============================================================================
def load_config():
    """
    加载配置文件
    
    从config.json读取配置，返回配置字典
    
    返回:
        dict: 配置字典，如果文件不存在或读取失败返回空字典
        
    错误处理：
    - 文件不存在：返回{}
    - JSON解析错误：打印错误并返回{}
    - 权限错误：打印错误并返回{}
    
    示例:
        config = load_config()
        api_key = config.get("api_key", "")
    """
    # 检查文件是否存在
    if not os.path.exists(CONFIG_FILE):
        return {}
    
    try:
        # 读取并解析JSON文件
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        return {}


# ============================================================================
# 保存配置
# ============================================================================
def save_config(data):
    """
    保存配置到文件
    
    将传入的配置数据合并到现有配置中，然后保存到文件
    
    参数:
        data: dict，要保存的配置数据
        
    返回:
        bool: 保存是否成功
        
    保存逻辑：
    1. 先加载现有配置
    2. 使用update()合并新配置（不覆盖全部，只更新指定字段）
    3. 写入文件（覆盖原有内容）
    
    这种方式确保：
    - 只更新需要修改的字段
    - 保留文件中其他未指定的配置项
    - 新配置优先于旧配置
    
    示例:
        save_config({"api_key": "new-key", "model": "new-model"})
    """
    try:
        # 加载现有配置
        current_config = load_config()
        
        # 合并新配置
        # update()方法会覆盖重复的键，保留不重复的键
        current_config.update(data)
        
        # 写入文件
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            # indent=4 使用4空格缩进，使JSON文件更易读
            json.dump(current_config, f, indent=4)
        
        return True
        
    except Exception as e:
        print(f"Error saving config: {e}")
        return False
