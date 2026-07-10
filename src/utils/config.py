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
    "active_profile": "默认",
    "profiles": {
        "默认": {
            "api_key": "your-api-key",
            "base_url": "https://openrouter.ai/api/v1",
            "model": "gemini-2.5-flash"
        }
    },
    "target_lang": "简体中文",
    "successful_models": ["gemini-2.5-flash"],
    "recent_folders": ["D:/manga/vol1", "D:/manga/vol2.cbz"],
    "auto_open_last": true
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

# 内存缓存：避免频繁读磁盘
_cached_config = None

# 翻译缓存上限（默认 2000 条）
MAX_CACHE_ENTRIES = 2000


# ============================================================================
# 加载配置
# ============================================================================
def load_config():
    """
    加载配置文件
    
    从config.json读取配置，返回配置字典
    """
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    if not os.path.exists(CONFIG_FILE):
        _cached_config = {}
        return _cached_config

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            _cached_config = json.load(f)
        return _cached_config
    except Exception as e:
        print(f"Error loading config: {e}")
        _cached_config = {}
        return _cached_config


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
            _cached_config = current_config
        
        return True
        
    except Exception as e:
        print(f"Error saving config: {e}")
        return False


def invalidate_config_cache():
    """供外部修改 config.json 后手动刷新内存缓存"""
    global _cached_config
    _cached_config = None


# ============================================================================
# 最近打开的文件夹管理
# ============================================================================
# 最多保留的最近路径数量
MAX_RECENT_FOLDERS = 10


def add_recent_folder(path: str):
    """
    将路径添加到最近打开列表

    逻辑：
    1. 加载现有配置
    2. 从列表中移除已有相同路径（去重）
    3. 插入到列表首位
    4. 截断到 MAX_RECENT_FOLDERS 条
    5. 保存

    参数:
        path: 文件夹或压缩包路径
    """
    config = load_config()
    recent = config.get("recent_folders", [])

    # 去重：移除已有相同路径
    if path in recent:
        recent.remove(path)

    # 插入到首位
    recent.insert(0, path)

    # 截断
    if len(recent) > MAX_RECENT_FOLDERS:
        recent = recent[:MAX_RECENT_FOLDERS]

    save_config({"recent_folders": recent})


# ============================================================================
# 阅读位置记忆（F7）
# ============================================================================
# 最多记录的文件夹阅读位置数
MAX_LAST_POSITIONS = 20


def save_last_position(folder_path: str, page_index: int):
    """
    保存某个文件夹的阅读位置

    逻辑：
    1. 加载现有配置
    2. 若已存在则先移除（移到末尾 → 标记最近写入）
    3. 写入新位置
    4. 超出 MAX_LAST_POSITIONS 时淘汰最旧的条目
    5. 持久化到 config.json

    参数:
        folder_path: 文件夹绝对路径（与 current_folder 一致）
        page_index: 文件列表中的索引（0-based），负值忽略
    """
    if page_index < 0:
        return

    config = load_config()
    positions = config.get("last_positions", {})

    # 如果已存在，先移除再插入（移到末尾，标记为最近写入）
    if folder_path in positions:
        del positions[folder_path]

    positions[folder_path] = page_index

    # LRU 淘汰：超出上限时移除最旧的（Python 3.7+ dict 保持插入顺序）
    while len(positions) > MAX_LAST_POSITIONS:
        oldest = next(iter(positions))
        del positions[oldest]

    save_config({"last_positions": positions})


def get_last_position(folder_path: str) -> int:
    """
    读取某个文件夹的阅读位置

    参数:
        folder_path: 文件夹绝对路径

    返回:
        上次阅读的页码索引（0-based），不存在返回 -1
    """
    config = load_config()
    positions = config.get("last_positions", {})
    return positions.get(folder_path, -1)
