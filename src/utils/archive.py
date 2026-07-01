#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - 压缩包工具模块

本模块提供漫画压缩包（.cbz / .zip）的检测与解压功能。

功能说明：
1. is_archive - 判断路径是否为支持的压缩包文件
2. extract_to_temp - 将压缩包解压到临时目录，返回目录和图片列表

注意事项：
- 仅支持 zip 格式（zipfile 标准库），无需额外依赖
- 解压目录使用 tempfile.mkdtemp 创建，调用方负责清理
- 过滤 __MACOSX/ 资源叉和 .DS_Store 垃圾文件
"""

# ============================================================================
# 标准库导入
# ============================================================================
import os             # 文件路径操作
import tempfile       # 临时目录
import zipfile        # ZIP 压缩包读写（标准库）

# ============================================================================
# 常量定义
# ============================================================================

# 支持的压缩包后缀（小写）
ARCHIVE_EXTS = ('.cbz', '.zip')

# 图片文件后缀（小写）
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')

# 临时目录前缀，方便排查
TEMP_DIR_PREFIX = "bubbletrans_arc_"


# ============================================================================
# 压缩包检测
# ============================================================================

def is_archive(path: str) -> bool:
    """
    判断路径是否为支持的压缩包文件

    同时检查后缀和文件格式（防止改名欺骗）

    参数:
        path: 文件路径

    返回:
        bool: 是否为支持的压缩包

    示例:
        >>> is_archive("comic.cbz")
        True
        >>> is_archive("comic.jpg")
        False
    """
    # 先检查后缀（快速排除）
    ext = os.path.splitext(path)[1].lower()
    if ext not in ARCHIVE_EXTS:
        return False

    # 再用 zipfile 验证实际格式（防止 .cbz 后缀但不是 zip 的情况）
    return zipfile.is_zipfile(path)


# ============================================================================
# 解压到临时目录
# ============================================================================

def extract_to_temp(archive_path: str) -> tuple:
    """
    将压缩包解压到临时目录

    处理流程：
    1. 校验文件格式
    2. 打开 zip，获取文件列表
    3. 过滤出图片文件（排除垃圾文件）
    4. 创建临时目录并解压
    5. 返回 (临时目录路径, 排序后的图片文件名列表)

    参数:
        archive_path: 压缩包文件路径

    返回:
        tuple: (temp_dir, image_files)
            - temp_dir: 临时目录路径（调用方负责清理）
            - image_files: 排序后的图片文件名列表

    异常:
        ValueError: 文件不是有效的 zip 格式
        zipfile.BadZipFile: zip 文件损坏
        OSError: 磁盘写入失败

    示例:
        >>> temp_dir, images = extract_to_temp("comic.cbz")
        >>> images
        ['001.jpg', '002.jpg', '003.jpg']
    """
    # 格式校验（双重保险：is_archive 已校验过，这里再做一次防外部调用）
    if not zipfile.is_zipfile(archive_path):
        raise ValueError(f"不是有效的压缩包文件: {os.path.basename(archive_path)}")

    with zipfile.ZipFile(archive_path, 'r') as zf:
        # 获取压缩包内所有文件名
        all_names = zf.namelist()

        # 过滤：仅保留图片文件，排除垃圾
        image_files = []
        for name in all_names:
            # 跳过目录条目
            if name.endswith('/'):
                continue

            # 跳过 macOS 资源叉目录内的文件和 .DS_Store
            if '/__MACOSX/' in name or name.startswith('__MACOSX/'):
                continue
            if os.path.basename(name).startswith('.DS_Store'):
                continue

            # 仅保留图片文件
            _, ext = os.path.splitext(name)
            if ext.lower() in IMAGE_EXTS:
                image_files.append(name)

        # 排序（保持阅读顺序）
        image_files.sort()

        if not image_files:
            raise ValueError(f"压缩包中未找到图片: {os.path.basename(archive_path)}")

        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX)

        # 逐文件解压（仅解压图片，不解压其他无关文件）
        for name in image_files:
            zf.extract(name, temp_dir)

    return temp_dir, image_files
