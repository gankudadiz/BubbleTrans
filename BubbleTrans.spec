# -*- mode: python ; coding: utf-8 -*-
"""
BubbleTrans PyInstaller 打包配置

体积控制原则：
1. 使用干净 venv（仅 requirements.txt 依赖）打包，避免 paddle/opencv 等历史残留
2. 显式 excludes 拦截误带的重型科学计算/CV 库
3. 业务源码不依赖 numpy/pandas；若分析阶段仍出现，说明打包环境不干净
"""

from PyInstaller.utils.hooks import collect_data_files

# qt-material 主题 QSS 等数据文件需要一并打包
qt_material_datas = collect_data_files('qt_material')

# 业务与运行时均不应打入的重型/历史依赖
EXCLUDES = [
    # 科学计算 / 表格（业务不用；曾被脏 venv 误带）
    'numpy',
    'pandas',
    'matplotlib',
    'scipy',
    'sklearn',
    'skimage',
    # CV / OCR 历史残留（项目已改为多模态 LLM，不再本地 OCR）
    'cv2',
    'paddle',
    'paddlepaddle',
    'paddlex',
    'paddleocr',
    'modelscope',
    'torch',
    'torchvision',
    'tensorflow',
    'onnxruntime',
    # 其它常见误带
    'fsspec',
    'networkx',
    'shapely',
    'safetensors',
    'huggingface_hub',
    'IPython',
    'jupyter',
    'notebook',
    'pytest',
    'unittest',
]

a = Analysis(
    ['src\\main.py'],
    pathex=[],
    binaries=[],
    datas=qt_material_datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

# 二次过滤：即使 hook 扫到路径，也从 binaries/datas/pure 中剔除
_BLOCK_NAME_FRAGMENTS = (
    'numpy',
    'pandas',
    'opencv',
    'cv2',
    'paddle',
    'modelscope',
    'torch',
    'scipy',
    'matplotlib',
    'sklearn',
    'fsspec',
    'shapely',
    'safetensors',
    'huggingface',
    'networkx',
)


def _is_blocked(entry) -> bool:
    # TOC entry: (dest_name, source_path, typecode) 或纯模块名字符串
    if isinstance(entry, (tuple, list)):
        name = str(entry[0]) if entry else ''
        src = str(entry[1]) if len(entry) > 1 else ''
        text = f'{name} {src}'.lower().replace('\\', '/')
    else:
        text = str(entry).lower().replace('\\', '/')
    return any(frag in text for frag in _BLOCK_NAME_FRAGMENTS)


a.binaries = [x for x in a.binaries if not _is_blocked(x)]
a.datas = [x for x in a.datas if not _is_blocked(x)]
a.pure = [x for x in a.pure if not _is_blocked(x)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BubbleTrans',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['file\\icon.ico'],
)
