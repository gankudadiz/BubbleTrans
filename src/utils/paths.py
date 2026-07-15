#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - 应用路径工具模块

本模块提供项目内部路径的统一获取函数，确保开发态与打包态行为一致。

核心函数：
- get_app_root(): 应用数据根目录（与 config.json / translation_cache.db 同级）
- get_project_cache_dir(): 项目本地缓存目录（<根>/cache/）

设计要点：
- 与 src/utils/cache.py:50-55 的 frozen 分支逻辑一致
- 打包态（sys.frozen）：指向 exe 同级目录，不落入 _MEI* 临时解压区
- 开发态：从本模块位置推导到仓库根
"""

import os
import sys


def get_app_root() -> str:
    """
    获取应用数据根目录（与 config.json / translation_cache.db 同级）

    PyInstaller 打包后（sys.frozen），__file__ 会落在 _MEI* 临时目录，
    因此必须用 sys.executable 修正到 exe 所在目录。

    返回:
        str: 应用数据根的绝对路径
    """
    if getattr(sys, 'frozen', False):
        # 打包态：exe 所在目录即数据根
        return os.path.dirname(os.path.abspath(sys.executable))

    # 开发态：paths.py → src/utils → src → 项目根
    _dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(_dir))


def get_project_cache_dir() -> str:
    """
    获取项目本地缓存目录（<应用数据根>/cache/），不存在则自动创建

    所有临时/缓存文件均统一存放在此目录，不再触碰系统 Temp。

    返回:
        str: 缓存目录的绝对路径
    """
    cache_dir = os.path.join(get_app_root(), "cache")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir
