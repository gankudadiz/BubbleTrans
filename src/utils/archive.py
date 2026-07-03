#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BubbleTrans - 压缩包工具模块

本模块提供漫画压缩包（.cbz / .zip / .cbr）的检测与解压功能。

功能说明：
1. is_archive - 判断路径是否为支持的压缩包文件
2. extract_to_temp - 将压缩包解压到临时目录，返回目录和图片列表

注意事项：
- .cbz / .zip 使用标准库 zipfile，零额外依赖
- .cbr 使用项目内嵌的 7z.exe（bin/ 目录），通过 subprocess 调用
- 解压目录使用 tempfile.mkdtemp 创建，调用方负责清理
- 过滤 __MACOSX/ 资源叉和 .DS_Store 垃圾文件
"""

# ============================================================================
# 标准库导入
# ============================================================================
import os             # 文件路径操作
import shutil          # 目录清理（RAR 解压失败时的资源回收）
import subprocess     # 调用外部 7z.exe（RAR/CBR 解压）
import sys            # 平台判断（CREATE_NO_WINDOW）
import tempfile       # 临时目录
import zipfile        # ZIP 压缩包读写（标准库）

# ============================================================================
# 常量定义
# ============================================================================

# 支持的压缩包后缀（小写）
ARCHIVE_EXTS = ('.cbz', '.zip', '.cbr')

# 图片文件后缀（小写）
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')

# 临时目录前缀，方便排查
TEMP_DIR_PREFIX = "bubbletrans_arc_"


# ============================================================================
# 内部工具
# ============================================================================

def _get_7z_path() -> str:
    """
    获取项目内嵌的 7z.exe 绝对路径

    基于 archive.py 位置推导：src/utils/ → src/ → 项目根 → bin/7z.exe
    """
    _dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(os.path.dirname(_dir))
    return os.path.join(_project_root, "bin", "7z.exe")


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
    """
    ext = os.path.splitext(path)[1].lower()
    if ext not in ARCHIVE_EXTS:
        return False

    if ext in ('.cbz', '.zip'):
        # zipfile 可验证 ZIP 格式完整性
        return zipfile.is_zipfile(path)

    if ext == '.cbr':
        # CBR 是 RAR 格式，Python 标准库无 RAR 检测手段
        # 只需确认文件存在，实际解压时 7z.exe 会校验格式
        return os.path.isfile(path)

    return False


# ============================================================================
# 统一解压入口
# ============================================================================

def extract_to_temp(archive_path: str) -> tuple:
    """
    将压缩包解压到临时目录

    根据后缀分发到 .cbz/.zip（zipfile）或 .cbr（7z.exe）处理路径。

    参数:
        archive_path: 压缩包文件路径

    返回:
        tuple: (temp_dir, image_files)
            - temp_dir: 临时目录路径（调用方负责清理）
            - image_files: 排序后的图片文件名列表

    异常:
        ValueError: 格式不支持或未找到图片
        RuntimeError: 7z.exe 缺失或执行超时
        OSError: 磁盘写入失败
    """
    ext = os.path.splitext(archive_path)[1].lower()

    if ext in ('.cbz', '.zip'):
        return _extract_zip(archive_path)

    if ext == '.cbr':
        return _extract_rar(archive_path)

    raise ValueError(f"不支持的压缩格式: {ext}")


# ============================================================================
# ZIP 解压（Python 标准库）
# ============================================================================

def _extract_zip(archive_path: str) -> tuple:
    """
    使用 zipfile 解压 .cbz / .zip 漫画压缩包

    处理流程：
    1. 校验 ZIP 格式
    2. 获取文件列表，过滤图片 + 排除垃圾文件
    3. 创建临时目录，仅解压图片文件
    4. 返回 (临时目录, 排序后的文件名列表)
    """
    if not zipfile.is_zipfile(archive_path):
        raise ValueError(f"不是有效的压缩包文件: {os.path.basename(archive_path)}")

    with zipfile.ZipFile(archive_path, 'r') as zf:
        all_names = zf.namelist()

        # 过滤：仅保留图片文件，排除垃圾
        image_files = []
        for name in all_names:
            if name.endswith('/'):
                continue
            if '/__MACOSX/' in name or name.startswith('__MACOSX/'):
                continue
            if os.path.basename(name).startswith('.DS_Store'):
                continue

            _, ext = os.path.splitext(name)
            if ext.lower() in IMAGE_EXTS:
                image_files.append(name)

        image_files.sort()

        if not image_files:
            raise ValueError(f"压缩包中未找到图片: {os.path.basename(archive_path)}")

        temp_dir = tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX)

        for name in image_files:
            zf.extract(name, temp_dir)

    return temp_dir, image_files


# ============================================================================
# RAR 解压（内嵌 7z.exe）
# ============================================================================

def _extract_rar(archive_path: str) -> tuple:
    """
    使用项目内嵌 7z.exe 解压 .cbr (RAR) 漫画压缩包

    处理流程：
    1. 定位 7z.exe
    2. 用 "7z e" 扁平解压全部内容到临时目录
    3. 遍历目录，收集图片文件（排除垃圾）
    4. 返回 (临时目录, 排序后的文件名列表)

    错误处理：解压过程中的任何异常都会先清理临时目录再向上抛出
    """
    seven_zip = _get_7z_path()
    if not os.path.exists(seven_zip):
        raise RuntimeError(
            f"7z 引擎未找到: {seven_zip}\n"
            "CBR 支持依赖 bin/7z.exe，请确保该文件存在"
        )

    archive_name = os.path.basename(archive_path)
    temp_dir = tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX)

    # Windows 下隐藏 7z 的控制台窗口
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    try:
        # "e" = Extract（扁平，不保留目录结构，文件名冲突时交互）
        # "-y" = 自动确认覆盖
        result = subprocess.run(
            [seven_zip, "e", archive_path, f"-o{temp_dir}", "-y"],
            capture_output=True, text=True, timeout=120,
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError(f"解压超时: {archive_name}")
    except OSError as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError(f"无法启动 7z.exe: {e}")

    # 检查 7z 退出码（非 0 表示失败）
    if result.returncode != 0:
        shutil.rmtree(temp_dir, ignore_errors=True)
        stderr = result.stderr.strip() or result.stdout.strip() or "未知错误"
        raise ValueError(f"解压失败: {archive_name}\n{stderr}")

    # 收集解压后的图片文件
    image_files = []
    for f in sorted(os.listdir(temp_dir)):
        full_path = os.path.join(temp_dir, f)
        if not os.path.isfile(full_path):
            continue
        _, ext = os.path.splitext(f)
        if ext.lower() in IMAGE_EXTS:
            if not f.startswith('.DS_Store'):
                image_files.append(f)

    if not image_files:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise ValueError(f"压缩包中未找到图片: {archive_name}")

    return temp_dir, image_files
