# -*- mode: python ; coding: utf-8 -*-

block_cipher = None


a = Analysis(['qualcoder\\__main__.py'],
             pathex=['C:\\Users\\ccurtain\\Downloads\\QualCoder-2.7'],
             binaries=[],
             datas=[('./qualcoder/locale/en/LC_MESSAGES/en.mo', 'qualcoder/locale/en/LC_MESSAGES/en.mo'), 
             ('./qualcoder/locale/de/LC_MESSAGES/de.mo', 'qualcoder/locale/de/LC_MESSAGES/de.mo'),
             ('./qualcoder/locale/el/LC_MESSAGES/el.mo', 'qualcoder/locale/el/LC_MESSAGES/el.mo'),
             ('./qualcoder/locale/es/LC_MESSAGES/es.mo', 'qualcoder/locale/es/LC_MESSAGES/es.mo'),
             ('./qualcoder/locale/fr/LC_MESSAGES/fr.mo', 'qualcoder/locale/fr/LC_MESSAGES/fr.mo'),
             ('./qualcoder/locale/it/LC_MESSAGES/it.mo', 'qualcoder/locale/it/LC_MESSAGES/it.mo'),
             ('./qualcoder/locale/jp/LC_MESSAGES/jp.mo', 'qualcoder/locale/jp/LC_MESSAGES/jp.mo'),
             ('./qualcoder/locale/pt/LC_MESSAGES/pt.mo', 'qualcoder/locale/pt/LC_MESSAGES/pt.mo')],
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
          name='__main__',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=True )


