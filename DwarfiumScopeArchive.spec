# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['dwarfium_scope_archive.py'],
    pathex=[],
    binaries=[],
    datas=[('L:\\AstroPhoto\\Tools\\JCL\\dwarfium_scope-archive-evolution\\dwarfium-scope-archive\\myenv3\\Lib\\site-packages\\nicegui', 'nicegui'), ('L:\\AstroPhoto\\Tools\\JCL\\dwarfium_scope-archive-evolution\\dwarfium-scope-archive\\myenv3\\Lib\\site-packages\\astroquery\\CITATION', 'astroquery'), ('astroquery/simbad/data/query_criteria_fields.json', 'astroquery/simbad/data')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DwarfiumScopeArchive',
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
    icon=['DwarfiumScopeArchive.ico'],
)
