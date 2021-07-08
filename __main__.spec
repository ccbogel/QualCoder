# -*- mode: python ; coding: utf-8 -*-

block_cipher = None


a = Analysis(['qualcoder\\__main__.py'],
             pathex=['C:\\Users\\ccurtain\\Downloads\\QualCoder-2.7'],
             binaries=[],
             datas=[('./qualcoder/locale/en/LC_MESSAGES/en.mo', 'qualcoder/locale/en/LC_MESSAGES/en.mo'), 
             ('./qualcoder/locale/de/LC_MESSAGES/de.mo', 'qualcoder/locale/de/LC_MESSAGES/de.mo'),
             ('./qualcoder/locale/de/app_de.qm', 'qualcoder/locale/de/app_de.qm'),
             ('./qualcoder/locale/el/LC_MESSAGES/el.mo', 'qualcoder/locale/el/LC_MESSAGES/el.mo'),
('./qualcoder/locale/el/app_el.qm', 'qualcoder/locale/el/app_el.qm'),
             ('./qualcoder/locale/es/LC_MESSAGES/es.mo', 'qualcoder/locale/es/LC_MESSAGES/es.mo'),
('./qualcoder/locale/es/app_es.qm', 'qualcoder/locale/es/app_es.qm'),
             ('./qualcoder/locale/fr/LC_MESSAGES/fr.mo', 'qualcoder/locale/fr/LC_MESSAGES/fr.mo'),
('./qualcoder/locale/fr/app_fr.qm', 'qualcoder/locale/fr/app_fr.qm'),
             ('./qualcoder/locale/it/LC_MESSAGES/it.mo', 'qualcoder/locale/it/LC_MESSAGES/it.mo'),
('./qualcoder/locale/it/app_it.qm', 'qualcoder/locale/it/app_it.qm'),
             ('./qualcoder/locale/jp/LC_MESSAGES/jp.mo', 'qualcoder/locale/jp/LC_MESSAGES/jp.mo'),
('./qualcoder/locale/jp/app_jp.qm', 'qualcoder/locale/jp/app_jp.qm'),
             ('./qualcoder/locale/pt/LC_MESSAGES/pt.mo', 'qualcoder/locale/pt/LC_MESSAGES/pt.mo'),
('./qualcoder/locale/pt/app_pt.qm', 'qualcoder/locale/pt/app_pt.qm')],
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


