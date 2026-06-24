# -*- mode: python ; coding: utf-8 -*-
"""
GoActivity PyInstaller 打包配置
使用方法: pyinstaller build.spec
"""

import sys
from pathlib import Path

block_cipher = None

# 项目根目录
root_dir = Path(SPECPATH)

# 收集数据文件
datas = [
    # 配置文件
    (str(root_dir / '.env.example'), '.'),
    # 文档
    (str(root_dir / 'README.md'), '.'),
    (str(root_dir / 'AGENTS.md'), '.'),
    # Alembic 迁移
    (str(root_dir / 'alembic'), 'alembic'),
    (str(root_dir / 'alembic.ini'), '.'),
    # 路由和服务模块
    (str(root_dir / 'app' / 'routes'), 'app/routes'),
    (str(root_dir / 'app' / 'services'), 'app/services'),
    (str(root_dir / 'app' / 'adapters'), 'app/adapters'),
    (str(root_dir / 'app' / 'utils'), 'app/utils'),
]

# 收集隐藏导入
hiddenimports = [
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'fastapi',
    'sqlalchemy',
    'sqlalchemy.dialects.sqlite',
    'pydantic',
    'pydantic_settings',
    'apscheduler',
    'apscheduler.schedulers.background',
    'apscheduler.triggers.cron',
    'httpx',
    'requests',
    'bs4',
    'PIL',
    'alembic',
    'alembic.operations',
    'alembic.runtime',
    # 项目模块
    'app.main',
    'app.config',
    'app.db',
    'app.models',
    'app.schemas',
    'app.exceptions',
    'app.logging_config',
    'app.routes.health',
    'app.routes.events',
    'app.routes.sync',
    'app.routes.reports',
    'app.routes.setup',
    'app.routes.webhooks',
    'app.routes.articles',
    'app.services.auto_sync',
    'app.services.bot_consumer',
    'app.services.scheduler',
    'app.services.event_extractor',
    'app.services.feishu_adapter',
    'app.services.article_service',
    'app.services.image_service',
    'app.adapters.feishu',
    'app.adapters.lark_cli',
    'app.utils.lark_cli',
]

a = Analysis(
    ['start_service.py'],
    pathex=[str(root_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL.ImageTk',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GoActivity',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 保持控制台窗口以便查看日志
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 可以添加图标文件路径
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GoActivity',
)
