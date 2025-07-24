# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, copy_metadata, collect_submodules
import sys
sys.setrecursionlimit(sys.getrecursionlimit() * 5)

block_cipher = None

datas = collect_data_files('langchain')
datas += collect_data_files('langchain_community')
datas += collect_data_files('langchain_core')
datas += collect_data_files('langchain_openai')
datas += collect_data_files('langchain_text_splitters')
datas += collect_data_files('transformers', include_py_files=True)
datas += collect_data_files('plotly')
# datas += collect_data_files('sentence_transformers')
datas += copy_metadata('tqdm')
datas += copy_metadata('regex')
datas += copy_metadata('requests')
datas += copy_metadata('packaging')
datas += copy_metadata('filelock')
datas += copy_metadata('numpy')
datas += copy_metadata('huggingface-hub')
# datas += copy_metadata('safetensors')
datas += copy_metadata('pyyaml')
datas += copy_metadata('torch')
datas += copy_metadata('tokenizers')
datas += [('LICENSE.txt', '.')]

hiddenimports = collect_submodules('transformers')
hiddenimports += collect_submodules('pydantic')
hiddenimports += ['scipy._lib.array_api_compat.numpy.fft']

a = Analysis(
    ['src/qualcoder/__main__.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

#splash = Splash('qualcoder.png',
#                binaries=a.binaries,
#                datas=a.datas,
#                text_pos=(10, 50),
#                text_size=12,
#                text_color='black')

exe = EXE(
    pyz,
#    splash,
    a.scripts,
    [],
    exclude_binaries=True,
    name='QualCoder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='qualcoder.png'
)

coll = COLLECT(
    exe,
#    splash.binaries,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='QualCoder',
)

app = BUNDLE(coll,
             name='Qualcoder.app',
             icon='qualcoder/GUI/qualcoder.icns',
             bundle_identifier='org.ccbogel.qualcoder')
