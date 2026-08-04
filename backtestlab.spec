# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['backtestlab.py'],
    pathex=[],
    binaries=[],
        datas=[('app.ico', '.'), ('assets', 'assets')],
    hiddenimports=['matplotlib.backends.backend_qtagg'],
    excludes=['tkinter','PyQt5','PyQt6','PySide2','scipy','pandas','IPython',
              'jupyter','notebook','pytest','PySide6.QtWebEngineCore',
              'PySide6.QtWebEngineWidgets','PySide6.QtQuick','PySide6.QtQml',
              'PySide6.Qt3DCore','PySide6.QtMultimedia','PySide6.QtCharts'],
    noarchive=False)

pyz = PYZ(a.pure)

exe = EXE(pyz, a.scripts, [],
    exclude_binaries=True,
    name='BacktestLab',
    debug=False, strip=False, upx=False,
    console=False,
    icon='app.ico',
    version='version_info.txt')

coll = COLLECT(exe, a.binaries, a.datas,
    strip=False, upx=False, name='BacktestLab')
