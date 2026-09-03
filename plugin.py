# -*- coding: utf-8 -*-
"""plugin module - split from AI_View_To_Paint.py (auto-generated)."""
import os
import time
import json
import base64
import traceback
import ssl
import urllib.request
import urllib.error
import glob
import shutil
import struct
import zlib
import threading
import queue as py_queue
from collections import deque
from itertools import combinations
import math

import substance_painter.ui
import substance_painter.project

try:
    import substance_painter.display as sp_display
except Exception:
    sp_display = None

try:
    import substance_painter.resource as sp_resource
except Exception:
    sp_resource = None

try:
    import substance_painter.textureset as sp_textureset
except Exception:
    sp_textureset = None

try:
    import substance_painter.layerstack as sp_layerstack
except Exception:
    sp_layerstack = None

try:
    import substance_painter.export as sp_export
except Exception:
    sp_export = None

from PySide6 import QtWidgets, QtCore, QtGui
from ai_view_to_paint.config import PLUGIN_TITLE
from ai_view_to_paint.panel import AIGenPanel

panel_widget = None


panel_dock = None


def start_plugin():
    global panel_widget, panel_dock

    panel_widget = AIGenPanel()
    panel_dock = substance_painter.ui.add_dock_widget(panel_widget)

    print("[{}] started".format(PLUGIN_TITLE))


def close_plugin():
    global panel_widget, panel_dock

    if panel_widget is not None:
        try:
            panel_widget.cleanup()
        except Exception as e:
            print("[{}] cleanup error: {}".format(PLUGIN_TITLE, e))

        try:
            substance_painter.ui.delete_ui_element(panel_widget)
        except Exception as e:
            print("[{}] delete panel widget error: {}".format(PLUGIN_TITLE, e))

        try:
            panel_widget.deleteLater()
        except Exception:
            pass

    panel_widget = None
    panel_dock = None

    try:
        QtWidgets.QApplication.processEvents()
    except Exception:
        pass

    print("[{}] closed".format(PLUGIN_TITLE))
