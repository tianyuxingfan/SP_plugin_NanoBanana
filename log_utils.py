# -*- coding: utf-8 -*-
"""log_utils module - split from AI_View_To_Paint.py (auto-generated)."""
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
from ai_view_to_paint.config import DEFAULT_LOG_LEVEL, LOG_DEBUG, LOG_ERROR, LOG_INFO, LOG_WARN

_log_level = DEFAULT_LOG_LEVEL


_ui_log_sink = None


def set_log_level(level):
    global _log_level
    try:
        _log_level = int(level)
    except Exception:
        _log_level = DEFAULT_LOG_LEVEL


def get_log_level():
    return _log_level


def set_ui_log_sink(fn):
    global _ui_log_sink
    _ui_log_sink = fn


def now_time_str():
    return time.strftime("%H:%M:%S")


def level_name(level):
    if level >= LOG_ERROR:
        return "ERROR"
    if level >= LOG_WARN:
        return "WARN"
    if level >= LOG_INFO:
        return "INFO"
    return "DEBUG"


def _format_log_line(level, tag, text):
    return "[{}] [{}] [{}] {}".format(
        now_time_str(),
        level_name(level),
        str(tag or "APP").upper(),
        str(text or "")
    )


def _emit_log(level, tag, text):
    if level < get_log_level():
        return

    line = _format_log_line(level, tag, text)

    try:
        print(line)
    except Exception:
        pass

    sink = _ui_log_sink
    if callable(sink):
        try:
            sink(line)
        except Exception:
            pass


def log_debug(tag, text):
    _emit_log(LOG_DEBUG, tag, text)


def log_info(tag, text):
    _emit_log(LOG_INFO, tag, text)


def log_warn(tag, text):
    _emit_log(LOG_WARN, tag, text)


def log_error(tag, text):
    _emit_log(LOG_ERROR, tag, text)


def short_text(text, limit=240):
    s = str(text or "")
    if len(s) <= limit:
        return s
    return s[:limit] + "...<truncated:{} chars>".format(len(s))


def short_json(data, limit=320):
    try:
        s = json.dumps(data, ensure_ascii=False, sort_keys=True)
    except Exception:
        s = str(data)
    return short_text(s, limit=limit)
