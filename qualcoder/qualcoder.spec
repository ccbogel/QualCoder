# -*- mode: python ; coding: utf-8 -*-

block_cipher = None


a = Analysis(['qualcoder.py'],
             pathex=['C:\\Users\\USER 1\\Documents\\informatics\\QualCoder-master\\qualcoder'],
             binaries=[],
             datas=[('\GUI\default.stylesheet','\GUI\default.stylesheet'),
             ('\GUI\About.html', '\GUI\About.html'),
             ('\GUI\en_Help.html', '\GUI\en_Help.html'),
             ('\GUI\NotoSans-hinted', '\GUI\NotoSans-hinted'),
             ('\Codebook.xsd', '\Codebook.xsd'),
             ('\Project-mrt2019.xsd', '\Project-mrt2019.xsd'),
             ('\locale','\locale'),
             ],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='qualcoder',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=True )
