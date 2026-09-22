"""Fail-closed maintenance latch shared with deployment scripts.

The Compose bind mount is read-only in the application containers. A process lock
alone is not enough: the durable latch survives an interrupted upgrade.
"""
from __future__ import annotations
from pathlib import Path
import os
import stat


def maintenance_state(directory=None, *, required=False):
    if directory is None or str(directory) == '':
        return {'status':'MISCONFIGURED' if required else 'DISABLED', 'blocked':required}
    path = Path(directory)
    try:
        mode = path.lstat().st_mode
        if not stat.S_ISDIR(mode) or stat.S_ISLNK(mode):
            return {'status':'UNREADABLE', 'blocked':True}
        # Proves that an empty or absent marker can actually be observed.
        with os.scandir(path) as entries:
            names = {entry.name for entry in entries}
        if 'active' in names:
            return {'status':'ACTIVE', 'blocked':True}
        return {'status':'OPEN', 'blocked':False}
    except OSError:
        return {'status':'UNREADABLE', 'blocked':True}


def configured_maintenance(cfg):
    directory = getattr(cfg, 'maintenance_dir', None) or os.environ.get('ND_MAINTENANCE_DIR')
    return maintenance_state(directory, required=cfg.env == 'production')
