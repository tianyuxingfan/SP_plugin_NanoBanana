# -*- coding: utf-8 -*-
"""utils module - split from AI_View_To_Paint.py (auto-generated)."""
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
from ai_view_to_paint.config import ALLOWED_MODELS, DEFAULT_IMAGE_SIZE, DEFAULT_MODEL, DEFAULT_OUTPUT_DIR, DEFAULT_POLL_INTERVAL, DEFAULT_POLL_TIMEOUT, DEFAULT_SETTINGS, PROVIDER_GRSAI, PROVIDER_PRESETS, PROVIDER_RUNNINGHUB, RESULT_PATH, RUNNINGHUB_DEFAULT_SUBMIT_PATH, RUNNINGHUB_LEGACY_SUBMIT_PATH, RUNNINGHUB_RESULT_PATH, RUNNINGHUB_TEXT_PATH, RUNNINGHUB_UPLOAD_BINARY, RUNNINGHUB_UPLOAD_DATA_URI, RUNNINGHUB_UPLOAD_PATH, SUBMIT_PATH

def parse_sse_data_json_lines(text):
    events = []

    for line in str(text or "").splitlines():
        line = line.strip()
        if not line:
            continue

        if not line.startswith("data:"):
            continue

        raw = line[len("data:"):].strip()
        if not raw or raw == "[DONE]":
            continue

        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                events.append(obj)
        except Exception:
            pass

    return events


def mask_secret(text, keep_left=6, keep_right=4):
    s = str(text or "")
    if not s:
        return ""
    if len(s) <= keep_left + keep_right:
        return "*" * len(s)
    return s[:keep_left] + "*" * (len(s) - keep_left - keep_right) + s[-keep_right:]


def sanitize_headers(headers):
    out = dict(headers or {})
    auth = out.get("Authorization")
    if auth:
        out["Authorization"] = mask_secret(auth, keep_left=10, keep_right=6)
    return out


def basename_list(paths, max_count=4):
    arr = []
    src = list(paths or [])
    for p in src[:max_count]:
        arr.append(os.path.basename(str(p or "")))
    extra = max(0, len(src) - len(arr))
    if extra > 0:
        arr.append("+{} more".format(extra))
    return ", ".join(arr)


def ui_path_text(path):
    path = str(path or "").strip()
    if not path:
        return ""
    return os.path.basename(path)


def ui_join_paths(paths):
    arr = []
    for p in list(paths or []):
        t = ui_path_text(p)
        if t:
            arr.append(t)
    return " | ".join(arr)


def image_paths_summary(paths):
    items = []
    for p in list(paths or []):
        w, h = get_image_size_safe(p)
        items.append("{}({}x{})".format(os.path.basename(str(p or "")), w, h))
    return ", ".join(items)


def ensure_dir(path):
    if not path:
        raise RuntimeError("输出目录不能为空")
    if not os.path.exists(path):
        os.makedirs(path)
    return path


def normalize_path_str(path):
    if not path:
        return ""
    return os.path.normcase(os.path.normpath(path))


def read_binary(path):
    with open(path, "rb") as f:
        return f.read()


def write_binary(path, data):
    with open(path, "wb") as f:
        f.write(data)
    return path


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def normalize_api_path(path, default=""):
    text = str(path or default or "").strip()
    if not text:
        return ""
    if not text.startswith("/"):
        text = "/" + text
    return text


def get_image_size_safe(image_path):
    try:
        if image_path and os.path.exists(image_path):
            img = QtGui.QImage(image_path)
            if not img.isNull():
                return img.width(), img.height()
    except Exception:
        pass
    return 0, 0


SETTINGS_FILENAME = "settings.json"


def plugin_settings_dir():
    # Settings file lives inside the ai_view_to_paint package folder.
    return os.path.dirname(os.path.abspath(__file__))


def plugin_settings_path():
    return os.path.join(plugin_settings_dir(), SETTINGS_FILENAME)


def legacy_plugin_settings_paths():
    # 历史版本的配置文件位置（按新旧顺序排列），仅用于自动迁移：
    # 1) 包目录内、旧命名 AI_View_To_Paint.json
    # 2) 更早版本：插件入口同级目录（包目录的上一级）
    return [
        os.path.join(plugin_settings_dir(), "AI_View_To_Paint.json"),
        os.path.join(os.path.dirname(plugin_settings_dir()), "AI_View_To_Paint.json"),
    ]


def merge_plugin_settings(data=None):
    settings = dict(DEFAULT_SETTINGS)
    if isinstance(data, dict):
        settings.update(data)

    provider = str(settings.get("provider", PROVIDER_GRSAI) or PROVIDER_GRSAI).strip()
    if provider not in PROVIDER_PRESETS:
        provider = PROVIDER_GRSAI
    settings["provider"] = provider

    preset = PROVIDER_PRESETS.get(provider, {})

    settings["api_base"] = str(settings.get("api_base", preset.get("api_base", "")) or "").strip().rstrip("/")
    settings["api_key"] = str(settings.get("api_key", "") or "").strip()
    settings["auth_mode"] = str(settings.get("auth_mode", preset.get("auth_mode", "bearer")) or "bearer").strip().lower()

    if provider == PROVIDER_GRSAI:
        settings["submit_path"] = SUBMIT_PATH
        settings["result_path"] = RESULT_PATH
        settings["use_data_url_prefix"] = False
    else:
        submit_path = normalize_api_path(
            settings.get("submit_path"),
            preset.get("submit_path", SUBMIT_PATH)
        )

        # 兼容历史配置：
        # 1) submit_path 缺失时默认值来自 GRSAI（/v1/api/generate），对 RunningHub 无效；
        # 2) 旧默认路径（低价渠道版，不稳定）自动迁移到官方稳定版；
        # 3) 用户自定义过的其他路径保持不变
        if submit_path in ("", SUBMIT_PATH, RUNNINGHUB_LEGACY_SUBMIT_PATH):
            submit_path = preset.get("submit_path", RUNNINGHUB_DEFAULT_SUBMIT_PATH)

        settings["submit_path"] = submit_path

        result_path = normalize_api_path(
            settings.get("result_path"),
            preset.get("result_path", RESULT_PATH)
        )
        if result_path in ("", RESULT_PATH):
            result_path = preset.get("result_path", RUNNINGHUB_RESULT_PATH)
        settings["result_path"] = result_path

    default_model = str(settings.get("default_model", DEFAULT_MODEL) or DEFAULT_MODEL).strip()
    if default_model not in ALLOWED_MODELS:
        default_model = DEFAULT_MODEL
    settings["default_model"] = default_model

    settings["default_image_size"] = str(
        settings.get("default_image_size", DEFAULT_IMAGE_SIZE) or DEFAULT_IMAGE_SIZE
    ).strip()

    settings["output_dir"] = str(
        settings.get("output_dir", DEFAULT_OUTPUT_DIR) or DEFAULT_OUTPUT_DIR
    ).strip()

    try:
        settings["poll_interval"] = max(0.2, float(settings.get("poll_interval", DEFAULT_POLL_INTERVAL)))
    except Exception:
        settings["poll_interval"] = DEFAULT_POLL_INTERVAL

    try:
        settings["poll_timeout"] = max(10, int(float(settings.get("poll_timeout", DEFAULT_POLL_TIMEOUT))))
    except Exception:
        settings["poll_timeout"] = DEFAULT_POLL_TIMEOUT

    # 注意：GRSAI 上面已经强制 False，这里只处理非 GRSAI
    if provider != PROVIDER_GRSAI:
        settings["use_data_url_prefix"] = bool(settings.get("use_data_url_prefix", False))

    settings["runninghub_upload_path"] = normalize_api_path(
        settings.get("runninghub_upload_path"),
        preset.get("upload_path", RUNNINGHUB_UPLOAD_PATH)
    )

    settings["runninghub_text_path"] = normalize_api_path(
        settings.get("runninghub_text_path"),
        preset.get("text_submit_path", RUNNINGHUB_TEXT_PATH)
    )

    upload_mode = str(
        settings.get("runninghub_upload_mode", preset.get("upload_mode", RUNNINGHUB_UPLOAD_DATA_URI)) or
        RUNNINGHUB_UPLOAD_DATA_URI
    ).strip().lower()

    if upload_mode not in (RUNNINGHUB_UPLOAD_DATA_URI, RUNNINGHUB_UPLOAD_BINARY):
        upload_mode = RUNNINGHUB_UPLOAD_DATA_URI

    settings["runninghub_upload_mode"] = upload_mode

    provider_api_keys = settings.get("provider_api_keys", {})
    if not isinstance(provider_api_keys, dict):
        provider_api_keys = {}

    normalized_provider_api_keys = {}
    for k, v in provider_api_keys.items():
        key_name = str(k or "").strip()
        if not key_name:
            continue
        normalized_provider_api_keys[key_name] = str(v or "").strip()

    settings["provider_api_keys"] = normalized_provider_api_keys

    current_provider = settings.get("provider", PROVIDER_GRSAI)
    current_api_key = str(settings.get("api_key", "") or "").strip()

    if current_api_key:
        settings["provider_api_keys"][current_provider] = current_api_key
    else:
        settings["api_key"] = settings["provider_api_keys"].get(current_provider, "")

    return settings


def load_plugin_settings():
    settings_path = plugin_settings_path()

    raw = read_json(settings_path, default=None)

    migrated_path = None
    if raw is None:
        # 当前配置不存在时，从历史位置按新旧顺序迁移
        for legacy_path in legacy_plugin_settings_paths():
            if os.path.exists(legacy_path):
                raw = read_json(legacy_path, default=None)
                if raw is not None:
                    migrated_path = legacy_path
                    break

    settings = merge_plugin_settings(raw or {})

    try:
        write_json(settings_path, settings)
        if migrated_path:
            # 迁移成功后移除旧文件，避免出现两份配置
            safe_remove(migrated_path)
    except Exception:
        pass

    return settings


def save_plugin_settings(data):
    settings = merge_plugin_settings(data)
    write_json(plugin_settings_path(), settings)
    return settings


def safe_remove(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
            return True
    except Exception:
        pass
    return False


def ssl_context():
    return ssl.create_default_context()


def unique_stamp():
    import uuid
    return "{}_{}".format(time.strftime("%Y%m%d_%H%M%S"), uuid.uuid4().hex[:6])


def now_str_readable():
    return time.strftime("%Y-%m-%d %H:%M:%S")
