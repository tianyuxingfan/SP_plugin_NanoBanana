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

API_BASE = "https://grsai.dakka.com.cn"
SUBMIT_PATH = "/v1/draw/nano-banana"
RESULT_PATH = "/v1/draw/result"

DEFAULT_MODEL = "nano-banana-2"
DEFAULT_ASPECT_RATIO = "auto"
DEFAULT_IMAGE_SIZE = "2K"

DEFAULT_POLL_INTERVAL = 1.5
DEFAULT_POLL_TIMEOUT = 300

DEFAULT_OUTPUT_DIR = os.path.expanduser("~/Pictures/sp_ai_outputs")

PROVIDER_GRSAI = "grsai"
PROVIDER_RUNNINGHUB = "runninghub"

RUNNINGHUB_API_BASE = "https://www.runninghub.cn"
RUNNINGHUB_DEFAULT_SUBMIT_PATH = "/openapi/v2/rhart-image-n-g31-flash/image-to-image"
RUNNINGHUB_RESULT_PATH = "/openapi/v2/query"
RUNNINGHUB_UPLOAD_PATH = "/openapi/v2/media/upload/binary"

RUNNINGHUB_UPLOAD_DATA_URI = "data_uri"
RUNNINGHUB_UPLOAD_BINARY = "upload_binary"

PROVIDER_PRESETS = {
    PROVIDER_GRSAI: {
        "label": "GRSAI",
        "api_base": "https://grsai.dakka.com.cn",
        "submit_path": "/v1/draw/nano-banana",
        "result_path": "/v1/draw/result",
        "auth_mode": "bearer",
    },
    PROVIDER_RUNNINGHUB: {
        "label": "RunningHub",
        "api_base": RUNNINGHUB_API_BASE,
        "submit_path": RUNNINGHUB_DEFAULT_SUBMIT_PATH,
        "result_path": RUNNINGHUB_RESULT_PATH,
        "upload_path": RUNNINGHUB_UPLOAD_PATH,
        "auth_mode": "bearer",
        "upload_mode": RUNNINGHUB_UPLOAD_DATA_URI,
    },
}

DEFAULT_SETTINGS = {
    "provider": PROVIDER_GRSAI,
    "api_base": API_BASE,
    "api_key": "",
    "auth_mode": "bearer",
    "submit_path": SUBMIT_PATH,
    "result_path": RESULT_PATH,
    "default_model": DEFAULT_MODEL,
    "default_image_size": DEFAULT_IMAGE_SIZE,
    "poll_interval": DEFAULT_POLL_INTERVAL,
    "poll_timeout": DEFAULT_POLL_TIMEOUT,
    "use_data_url_prefix": False,
    "output_dir": DEFAULT_OUTPUT_DIR,

    "runninghub_upload_path": RUNNINGHUB_UPLOAD_PATH,
    "runninghub_upload_mode": RUNNINGHUB_UPLOAD_DATA_URI,

    "provider_api_keys": {},
}

PLUGIN_TITLE = "AI View To Paint"
PANEL_OBJECT_NAME = "ai_view_to_paint_panel_v40"

THUMB_SIZE = 132
THUMB_GRID_W = 150
THUMB_GRID_H = 150

MODE_SINGLE = "单视角生成"
MODE_MULTI = "多视角映射"
MODE_UV_GUIDE = "UV贴图生成"
MODE_PROMPT_ONLY = "提示词生成"

DEFAULT_SINGLE_PROMPT = """根据当前模型视角图生成贴图效果，保持主体结构、轮廓与构图一致。

材质指定："""

DEFAULT_SINGLE_REF_PROMPT = """参考输入中的参考图风格与材质表现，重绘当前模型视角图。

要求：
1. 严格保持当前模型视角图的结构、轮廓、视角与构图不变
2. 参考参考图的材质、配色、细节和风格
3. 不改变主体比例，不新增或删减主体结构

材质指定："""

DEFAULT_MULTI_PROMPT = """根据输入的多视角控制图生成统一贴图效果，保持不同视角下材质、颜色和细节一致。

材质指定："""

DEFAULT_MULTI_REF_PROMPT = """参考输入中的参考图风格与材质表现，并根据多视角控制图生成统一贴图效果。

要求：
1. 保持不同视角下材质、颜色和细节一致
2. 严格遵守多视角控制图中的结构、轮廓与布局
3. 不改变主体比例，不新增或删减主体结构

材质指定："""

DEFAULT_UV_GUIDE_PROMPT = """根据输入图生成最终UV贴图。

输入说明：
1. 第一张图是UV布局图
2. 第二张图是模型四视角参考图，用于判断部位与UV区域的对应关系

要求：
1. 严格保持UV区域、边界、布局与留白不变
2. 根据四视角参考图，将正确的颜色、材质和结构放到对应UV区域
3. 保证前后左右映射关系准确，不要错位、颠倒或混乱
4. 输入图中的颜色仅用于定位，不代表最终颜色

材质指定："""

DEFAULT_UV_GUIDE_REF_PROMPT = """根据输入图生成最终UV贴图，并参考附加参考图的材质、风格与细节表现。

输入说明：
1. 第一张图是UV布局图，决定最终输出的区域、边界与排布
2. 第二张图是模型四视角参考图，用于判断各部位与UV区域的对应关系
3. 其余参考图用于提供材质、配色、风格与细节参考

要求：
1. 严格保持UV区域、边界、布局与留白不变
2. 根据四视角参考图，将正确的颜色、材质和结构放到对应UV区域
3. 在不破坏UV布局和映射关系的前提下，参考附加参考图的材质、配色与风格
4. 输入图中的颜色仅用于定位，不代表最终颜色

材质指定："""

DEFAULT_NORMAL_PROMPT = """根据输入贴图生成一张细节法线贴图（normal），只提取表面细节，不要重建主体大结构。

要求：
1. 保持原图的布局、图案位置和边界位置不变
2. 只保留适合作为表面浮雕、刻线和纹理起伏的高频细节
3. 不新增不存在的结构，不改变原有图案设计
4. 输出适合游戏材质使用的切线空间法线贴图
"""

DEFAULT_PROMPT_ONLY_PROMPT = ""
DEFAULT_PROMPT_ONLY_REF_PROMPT = """请综合参考输入中的参考图，生成一致的材质、风格与细节效果。"""


MULTIVIEW_SET_4 = [
    ("front", "正视图"),
    ("back", "后视图"),
    ("left", "左视图"),
    ("right", "右视图"),
]

MULTIVIEW_SET_6 = [
    ("front", "正视图"),
    ("back", "后视图"),
    ("left", "左视图"),
    ("right", "右视图"),
    ("top", "顶视图"),
    ("bottom", "底视图"),
]

DEFAULT_MULTI_TILE_SIZE = 1024
DEFAULT_UV_GUIDE_TILE_SIZE = 1024
DEFAULT_ATLAS_BG = "#242424"

MULTIVIEW_SUBJECT_BG_TOLERANCE = 18
MULTIVIEW_SUBJECT_PADDING = 12
MULTIVIEW_SUBJECT_SAMPLE_STEP = 2

MULTIVIEW_PACK_GAP = 18
MULTIVIEW_PACK_OUTER_PADDING = 20
MULTIVIEW_MAX_UPSCALE = 1.0
MULTIVIEW_PACK_SIDE_4 = 2048
MULTIVIEW_PACK_SIDE_6 = 2560

MULTIVIEW_VIEWPORT_TRIM_LEFT = 6
MULTIVIEW_VIEWPORT_TRIM_TOP = 24
MULTIVIEW_VIEWPORT_TRIM_RIGHT = 6
MULTIVIEW_VIEWPORT_TRIM_BOTTOM = 16

MULTIVIEW_ROT_PRESETS = {
    "front": [0.0, 0.0, 0.0],
    "back": [0.0, 180.0, 0.0],
    "left": [0.0, 90.0, 0.0],
    "right": [0.0, -90.0, 0.0],
    "top": [-90.0, 0.0, 0.0],
    "bottom": [90.0, 0.0, 0.0],
}

PROJECTOR_ROTATION_EULER_OFFSET = [0.0, 0.0, 0.0]
PROJECTOR_GLOBAL_SCALE_MULTIPLIER = 0.5
PROJECTOR_VIEW_FIT_SCALE = 2.2
PROJECTOR_DEPTH_SCALE = 3.0

UV_EXPORT_PRESET_NAME = "2D View"

panel_widget = None
panel_dock = None


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


def plugin_settings_dir():
    return os.path.dirname(os.path.abspath(__file__))


def plugin_settings_path():
    return os.path.join(plugin_settings_dir(), "AI_View_To_Paint.json")


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
    settings["submit_path"] = normalize_api_path(settings.get("submit_path"), preset.get("submit_path", SUBMIT_PATH))
    settings["result_path"] = normalize_api_path(settings.get("result_path"), preset.get("result_path", RESULT_PATH))
    settings["default_model"] = str(settings.get("default_model", DEFAULT_MODEL) or DEFAULT_MODEL).strip()
    settings["default_image_size"] = str(settings.get("default_image_size", DEFAULT_IMAGE_SIZE) or DEFAULT_IMAGE_SIZE).strip()
    settings["output_dir"] = str(settings.get("output_dir", DEFAULT_OUTPUT_DIR) or DEFAULT_OUTPUT_DIR).strip()

    try:
        settings["poll_interval"] = max(0.2, float(settings.get("poll_interval", DEFAULT_POLL_INTERVAL)))
    except Exception:
        settings["poll_interval"] = DEFAULT_POLL_INTERVAL

    try:
        settings["poll_timeout"] = max(10, int(float(settings.get("poll_timeout", DEFAULT_POLL_TIMEOUT))))
    except Exception:
        settings["poll_timeout"] = DEFAULT_POLL_TIMEOUT

    settings["use_data_url_prefix"] = bool(settings.get("use_data_url_prefix", False))

    settings["runninghub_upload_path"] = normalize_api_path(
        settings.get("runninghub_upload_path"),
        preset.get("upload_path", RUNNINGHUB_UPLOAD_PATH)
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
    return merge_plugin_settings(read_json(plugin_settings_path(), default={}))


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


def http_post_json(url, headers, payload, timeout=120):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url=url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:
            status_code = resp.getcode()
            body = resp.read()
            text = body.decode("utf-8", errors="replace")
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            return status_code, text, parsed
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError("HTTPError {}: {}".format(e.code, body))
    except urllib.error.URLError as e:
        raise RuntimeError("URLError: {}".format(e))


def http_post_multipart(url, headers=None, fields=None, files=None, timeout=120):
    import uuid

    boundary = "----WebKitFormBoundary{}".format(uuid.uuid4().hex)
    body = bytearray()

    def add_field(name, value):
        body.extend(("--{}\r\n".format(boundary)).encode("utf-8"))
        body.extend(('Content-Disposition: form-data; name="{}"\r\n\r\n'.format(name)).encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")

    def add_file(name, filename, content, content_type="application/octet-stream"):
        body.extend(("--{}\r\n".format(boundary)).encode("utf-8"))
        body.extend(
            ('Content-Disposition: form-data; name="{}"; filename="{}"\r\n'.format(name, filename)).encode("utf-8")
        )
        body.extend(("Content-Type: {}\r\n\r\n".format(content_type)).encode("utf-8"))
        body.extend(content)
        body.extend(b"\r\n")

    for k, v in (fields or {}).items():
        add_field(k, v)

    for f in (files or []):
        add_file(
            f["name"],
            f.get("filename", "file.bin"),
            f.get("content", b""),
            f.get("content_type", "application/octet-stream")
        )

    body.extend(("--{}--\r\n".format(boundary)).encode("utf-8"))

    req_headers = dict(headers or {})
    req_headers["Content-Type"] = "multipart/form-data; boundary={}".format(boundary)

    req = urllib.request.Request(url=url, data=bytes(body), headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:
            status_code = resp.getcode()
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            return status_code, text, parsed
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError("HTTPError {}: {}".format(e.code, body))
    except urllib.error.URLError as e:
        raise RuntimeError("URLError: {}".format(e))


def http_get_bytes(url, timeout=120):
    req = urllib.request.Request(url=url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError("HTTPError {}: {}".format(e.code, body))
    except urllib.error.URLError as e:
        raise RuntimeError("URLError: {}".format(e))


def sanitize_png_bytes(data):
    png_sig = b"\x89PNG\r\n\x1a\n"
    if not data or not data.startswith(png_sig):
        return data

    keep_known = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS"}

    out = bytearray()
    out.extend(png_sig)

    pos = 8
    got_iend = False

    try:
        while pos + 8 <= len(data):
            length = struct.unpack(">I", data[pos:pos + 4])[0]
            ctype = data[pos + 4:pos + 8]
            start = pos + 8
            end = start + length
            crc_end = end + 4

            if crc_end > len(data):
                break

            cdata = data[start:end]
            is_critical = (ctype[0] & 0x20) == 0

            if is_critical or ctype in keep_known:
                out.extend(struct.pack(">I", len(cdata)))
                out.extend(ctype)
                out.extend(cdata)
                crc = zlib.crc32(ctype)
                crc = zlib.crc32(cdata, crc) & 0xffffffff
                out.extend(struct.pack(">I", crc))

            pos = crc_end
            if ctype == b"IEND":
                got_iend = True
                break

        if got_iend:
            return bytes(out)
    except Exception:
        pass

    return data


def load_pixmap_safe(path):
    pixmap = QtGui.QPixmap(path)
    if pixmap.isNull():
        raise RuntimeError("无法加载图片: {}".format(path))
    return pixmap


def fit_pixmap_to_canvas(pixmap, width, height, bg="#000000"):
    if pixmap is None or pixmap.isNull():
        raise RuntimeError("fit_pixmap_to_canvas 输入图片无效")

    scaled = pixmap.scaled(
        QtCore.QSize(width, height),
        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        QtCore.Qt.TransformationMode.SmoothTransformation
    )

    canvas = QtGui.QPixmap(width, height)
    canvas.fill(QtGui.QColor(bg))

    painter = QtGui.QPainter(canvas)
    try:
        x = int((width - scaled.width()) / 2)
        y = int((height - scaled.height()) / 2)
        painter.drawPixmap(x, y, scaled)
    finally:
        painter.end()

    return canvas


def normalize_square_contain_with_manifest(pixmap, size, bg=DEFAULT_ATLAS_BG):
    if pixmap is None or pixmap.isNull():
        raise RuntimeError("normalize_square_contain_with_manifest 输入图片无效")

    side = max(1, int(size))
    src_w = pixmap.width()
    src_h = pixmap.height()
    if src_w <= 0 or src_h <= 0:
        raise RuntimeError("输入图片尺寸无效")

    scaled = pixmap.scaled(
        QtCore.QSize(side, side),
        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        QtCore.Qt.TransformationMode.SmoothTransformation
    )

    scaled_w = scaled.width()
    scaled_h = scaled.height()

    canvas = QtGui.QPixmap(side, side)
    canvas.fill(QtGui.QColor(bg))

    pad_left = int(round((side - scaled_w) * 0.5))
    pad_top = int(round((side - scaled_h) * 0.5))
    pad_right = max(0, side - scaled_w - pad_left)
    pad_bottom = max(0, side - scaled_h - pad_top)

    painter = QtGui.QPainter(canvas)
    try:
        painter.drawPixmap(pad_left, pad_top, scaled)
    finally:
        painter.end()

    manifest = {
        "type": "single_view_manifest",
        "fit_mode": "contain_square",
        "source_size": [src_w, src_h],
        "output_size": [side, side],
        "scaled_size": [scaled_w, scaled_h],
        "content_rect": [pad_left, pad_top, scaled_w, scaled_h],
        "pad_left": pad_left,
        "pad_top": pad_top,
        "pad_right": pad_right,
        "pad_bottom": pad_bottom,
    }

    return canvas, manifest


def trim_pixmap_margins(
    pixmap,
    left=MULTIVIEW_VIEWPORT_TRIM_LEFT,
    top=MULTIVIEW_VIEWPORT_TRIM_TOP,
    right=MULTIVIEW_VIEWPORT_TRIM_RIGHT,
    bottom=MULTIVIEW_VIEWPORT_TRIM_BOTTOM
):
    if pixmap is None or pixmap.isNull():
        raise RuntimeError("trim_pixmap_margins 输入图片无效")

    src_w = pixmap.width()
    src_h = pixmap.height()
    if src_w <= 0 or src_h <= 0:
        raise RuntimeError("输入图片尺寸无效")

    left = max(0, int(left))
    top = max(0, int(top))
    right = max(0, int(right))
    bottom = max(0, int(bottom))

    x = left
    y = top
    w = max(1, src_w - left - right)
    h = max(1, src_h - top - bottom)

    rect = QtCore.QRect(x, y, w, h)
    trimmed = pixmap.copy(rect)

    return trimmed, {
        "original_size": [src_w, src_h],
        "trim_rect": [x, y, w, h],
    }


def _avg_block_rgb(image, x0, y0, w, h):
    img_w = image.width()
    img_h = image.height()
    if img_w <= 0 or img_h <= 0:
        return [36, 36, 36]

    x0 = max(0, min(int(x0), img_w - 1))
    y0 = max(0, min(int(y0), img_h - 1))
    w = max(1, min(int(w), img_w - x0))
    h = max(1, min(int(h), img_h - y0))

    rs, gs, bs = [], [], []
    for yy in range(y0, y0 + h):
        for xx in range(x0, x0 + w):
            c = QtGui.QColor(image.pixel(xx, yy))
            rs.append(c.red())
            gs.append(c.green())
            bs.append(c.blue())

    if not rs:
        return [36, 36, 36]

    return [
        int(sum(rs) / len(rs)),
        int(sum(gs) / len(gs)),
        int(sum(bs) / len(bs)),
    ]


def _estimate_border_bg_rgb(image, block_size=8):
    w = image.width()
    h = image.height()
    if w <= 0 or h <= 0:
        return [36, 36, 36]

    b = max(1, int(block_size))

    samples = [
        _avg_block_rgb(image, 0, 0, b, b),
        _avg_block_rgb(image, max(0, w - b), 0, b, b),
        _avg_block_rgb(image, 0, max(0, h - b), b, b),
        _avg_block_rgb(image, max(0, w - b), max(0, h - b), b, b),

        _avg_block_rgb(image, max(0, int(w * 0.5) - b // 2), 0, b, b),
        _avg_block_rgb(image, max(0, int(w * 0.5) - b // 2), max(0, h - b), b, b),
        _avg_block_rgb(image, 0, max(0, int(h * 0.5) - b // 2), b, b),
        _avg_block_rgb(image, max(0, w - b), max(0, int(h * 0.5) - b // 2), b, b),
    ]

    return [
        int(sum(v[0] for v in samples) / len(samples)),
        int(sum(v[1] for v in samples) / len(samples)),
        int(sum(v[2] for v in samples) / len(samples)),
    ]


def _rgb_to_hex(rgb):
    r = max(0, min(int(rgb[0]), 255))
    g = max(0, min(int(rgb[1]), 255))
    b = max(0, min(int(rgb[2]), 255))
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


def _color_near_rgb(rgb, bg_rgb, tolerance):
    return (
        abs(int(rgb[0]) - int(bg_rgb[0])) <= tolerance and
        abs(int(rgb[1]) - int(bg_rgb[1])) <= tolerance and
        abs(int(rgb[2]) - int(bg_rgb[2])) <= tolerance
    )


def detect_subject_bbox_from_border_floodfill(
    pixmap,
    tolerance=MULTIVIEW_SUBJECT_BG_TOLERANCE,
    padding=MULTIVIEW_SUBJECT_PADDING,
    sample_step=MULTIVIEW_SUBJECT_SAMPLE_STEP
):
    if pixmap is None or pixmap.isNull():
        raise RuntimeError("detect_subject_bbox_from_border_floodfill 输入图片无效")

    image = pixmap.toImage().convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
    w = image.width()
    h = image.height()
    if w <= 0 or h <= 0:
        return [0, 0, max(1, w), max(1, h)], {
            "bg_rgb": [36, 36, 36],
            "bg_hex": DEFAULT_ATLAS_BG,
        }

    step = max(1, int(sample_step))
    tol = max(0, int(tolerance))
    pad = max(0, int(padding))

    bg_rgb = _estimate_border_bg_rgb(image, block_size=8)

    grid_w = int(math.ceil(float(w) / float(step)))
    grid_h = int(math.ceil(float(h) / float(step)))

    def sample_cell_rgb(cx, cy):
        px = min(w - 1, cx * step + step // 2)
        py = min(h - 1, cy * step + step // 2)
        c = QtGui.QColor(image.pixel(px, py))
        return [c.red(), c.green(), c.blue()]

    visited = [[False for _ in range(grid_w)] for _ in range(grid_h)]
    is_bg = [[False for _ in range(grid_w)] for _ in range(grid_h)]

    q = deque()

    def try_seed(cx, cy):
        if cx < 0 or cy < 0 or cx >= grid_w or cy >= grid_h:
            return
        if visited[cy][cx]:
            return
        visited[cy][cx] = True
        rgb = sample_cell_rgb(cx, cy)
        if _color_near_rgb(rgb, bg_rgb, tol):
            is_bg[cy][cx] = True
            q.append((cx, cy))

    for cx in range(grid_w):
        try_seed(cx, 0)
        try_seed(cx, grid_h - 1)

    for cy in range(grid_h):
        try_seed(0, cy)
        try_seed(grid_w - 1, cy)

    while q:
        cx, cy = q.popleft()
        for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
            if nx < 0 or ny < 0 or nx >= grid_w or ny >= grid_h:
                continue
            if visited[ny][nx]:
                continue
            visited[ny][nx] = True
            rgb = sample_cell_rgb(nx, ny)
            if _color_near_rgb(rgb, bg_rgb, tol):
                is_bg[ny][nx] = True
                q.append((nx, ny))

    fg_visited = [[False for _ in range(grid_w)] for _ in range(grid_h)]
    components = []

    img_cx = (grid_w - 1) * 0.5
    img_cy = (grid_h - 1) * 0.5

    for sy in range(grid_h):
        for sx in range(grid_w):
            if is_bg[sy][sx]:
                continue
            if fg_visited[sy][sx]:
                continue

            dq = deque()
            dq.append((sx, sy))
            fg_visited[sy][sx] = True

            count = 0
            min_cx = grid_w
            min_cy = grid_h
            max_cx = -1
            max_cy = -1
            sum_x = 0.0
            sum_y = 0.0

            touches_border = False

            while dq:
                cx, cy = dq.popleft()
                count += 1
                sum_x += cx
                sum_y += cy

                if cx < min_cx:
                    min_cx = cx
                if cy < min_cy:
                    min_cy = cy
                if cx > max_cx:
                    max_cx = cx
                if cy > max_cy:
                    max_cy = cy

                if cx == 0 or cy == 0 or cx == grid_w - 1 or cy == grid_h - 1:
                    touches_border = True

                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if nx < 0 or ny < 0 or nx >= grid_w or ny >= grid_h:
                        continue
                    if fg_visited[ny][nx]:
                        continue
                    if is_bg[ny][nx]:
                        continue
                    fg_visited[ny][nx] = True
                    dq.append((nx, ny))

            if count <= 0:
                continue

            center_x = sum_x / float(count)
            center_y = sum_y / float(count)

            dist2 = (center_x - img_cx) ** 2 + (center_y - img_cy) ** 2
            bbox_w = max_cx - min_cx + 1
            bbox_h = max_cy - min_cy + 1
            bbox_area = bbox_w * bbox_h

            components.append({
                "count": count,
                "bbox": [min_cx, min_cy, bbox_w, bbox_h],
                "center": [center_x, center_y],
                "dist2": dist2,
                "touches_border": touches_border,
                "bbox_area": bbox_area,
            })

    if not components:
        return [0, 0, w, h], {
            "bg_rgb": bg_rgb,
            "bg_hex": _rgb_to_hex(bg_rgb),
        }

    max_count = max(c["count"] for c in components)
    keep = []
    min_keep = max(4, int(max_count * 0.06))

    for c in components:
        if c["count"] < min_keep:
            continue
        keep.append(c)

    if not keep:
        keep = list(components)

    def comp_score(c):
        area_score = float(c["count"])
        center_penalty = c["dist2"] * 0.35
        border_penalty = 0.0
        if c["touches_border"]:
            border_penalty += area_score * 0.25
        return area_score - center_penalty - border_penalty

    best = max(keep, key=comp_score)

    min_cx, min_cy, bbox_w, bbox_h = best["bbox"]
    max_cx = min_cx + bbox_w - 1
    max_cy = min_cy + bbox_h - 1

    x0 = max(0, min_cx * step - pad)
    y0 = max(0, min_cy * step - pad)
    x1 = min(w, (max_cx + 1) * step + pad)
    y1 = min(h, (max_cy + 1) * step + pad)

    x1 = max(x0 + 1, x1)
    y1 = max(y0 + 1, y1)

    return [x0, y0, x1 - x0, y1 - y0], {
        "bg_rgb": bg_rgb,
        "bg_hex": _rgb_to_hex(bg_rgb),
    }


def crop_subject_from_capture(pixmap):
    if pixmap is None or pixmap.isNull():
        raise RuntimeError("crop_subject_from_capture 输入图片无效")

    trimmed, trim_meta = trim_pixmap_margins(
        pixmap,
        left=MULTIVIEW_VIEWPORT_TRIM_LEFT,
        top=MULTIVIEW_VIEWPORT_TRIM_TOP,
        right=MULTIVIEW_VIEWPORT_TRIM_RIGHT,
        bottom=MULTIVIEW_VIEWPORT_TRIM_BOTTOM
    )

    crop_rect_in_trimmed, bg_meta = detect_subject_bbox_from_border_floodfill(
        trimmed,
        tolerance=MULTIVIEW_SUBJECT_BG_TOLERANCE,
        padding=MULTIVIEW_SUBJECT_PADDING,
        sample_step=MULTIVIEW_SUBJECT_SAMPLE_STEP
    )

    cx, cy, cw, ch = [int(v) for v in crop_rect_in_trimmed]
    cropped = trimmed.copy(cx, cy, cw, ch)

    trim_rect = trim_meta.get("trim_rect", [0, 0, pixmap.width(), pixmap.height()])
    final_crop_rect = [
        int(trim_rect[0]) + cx,
        int(trim_rect[1]) + cy,
        cw,
        ch
    ]

    return cropped, {
        "original_capture_size": trim_meta.get("original_size", [pixmap.width(), pixmap.height()]),
        "trim_rect_in_capture": trim_rect,
        "crop_rect_in_capture": final_crop_rect,
        "bg_rgb": bg_meta.get("bg_rgb", [36, 36, 36]),
        "bg_hex": bg_meta.get("bg_hex", DEFAULT_ATLAS_BG),
    }


def restore_generated_tile_to_capture_canvas(tile_image_or_path, tile_manifest, output_path):
    if isinstance(tile_image_or_path, QtGui.QImage):
        tile_image = tile_image_or_path
    else:
        tile_image = QtGui.QImage(tile_image_or_path)

    if tile_image.isNull():
        raise RuntimeError("restore_generated_tile_to_capture_canvas 输入 tile 无效")

    if not isinstance(tile_manifest, dict):
        raise RuntimeError("tile_manifest 无效")

    original_capture_size = tile_manifest.get("original_capture_size", [])
    crop_rect_in_capture = tile_manifest.get("crop_rect_in_capture", [])
    tile_content_rect = tile_manifest.get("tile_content_rect", [])
    tile_output_size = tile_manifest.get("tile_output_size", [])

    if len(original_capture_size) != 2:
        raise RuntimeError("tile_manifest 缺少 original_capture_size")
    if len(crop_rect_in_capture) != 4:
        raise RuntimeError("tile_manifest 缺少 crop_rect_in_capture")

    orig_w, orig_h = [int(v) for v in original_capture_size]
    crop_x, crop_y, crop_w, crop_h = [int(v) for v in crop_rect_in_capture]

    if orig_w <= 0 or orig_h <= 0 or crop_w <= 0 or crop_h <= 0:
        raise RuntimeError("restore 所需尺寸无效")

    content_img = tile_image

    if len(tile_content_rect) == 4 and len(tile_output_size) == 2:
        tx, ty, tw, th = [int(v) for v in tile_content_rect]
        ref_tw, ref_th = [int(v) for v in tile_output_size]

        img_w = tile_image.width()
        img_h = tile_image.height()

        if ref_tw > 0 and ref_th > 0 and img_w > 0 and img_h > 0:
            sx = float(img_w) / float(ref_tw)
            sy = float(img_h) / float(ref_th)

            x0 = int(round(tx * sx))
            y0 = int(round(ty * sy))
            x1 = int(round((tx + tw) * sx))
            y1 = int(round((ty + th) * sy))

            x0 = max(0, min(x0, max(img_w - 1, 0)))
            y0 = max(0, min(y0, max(img_h - 1, 0)))
            x1 = max(x0 + 1, min(x1, img_w))
            y1 = max(y0 + 1, min(y1, img_h))

            sub = tile_image.copy(x0, y0, x1 - x0, y1 - y0)
            if not sub.isNull():
                content_img = sub

    scaled_pm = QtGui.QPixmap.fromImage(content_img).scaled(
        crop_w,
        crop_h,
        QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
        QtCore.Qt.TransformationMode.SmoothTransformation
    )

    source_capture_path = str(tile_manifest.get("capture_path", "") or "").strip()

    if source_capture_path and os.path.exists(source_capture_path):
        canvas = load_pixmap_safe(source_capture_path)
        if canvas.width() != orig_w or canvas.height() != orig_h:
            fixed = QtGui.QPixmap(orig_w, orig_h)
            fixed.fill(QtGui.QColor(tile_manifest.get("bg_hex", DEFAULT_ATLAS_BG)))
            painter = QtGui.QPainter(fixed)
            try:
                painter.drawPixmap(0, 0, canvas)
            finally:
                painter.end()
            canvas = fixed
    else:
        canvas = QtGui.QPixmap(orig_w, orig_h)
        canvas.fill(QtGui.QColor(tile_manifest.get("bg_hex", DEFAULT_ATLAS_BG)))

    painter = QtGui.QPainter(canvas)
    try:
        painter.drawPixmap(crop_x, crop_y, scaled_pm)
    finally:
        painter.end()

    ok = canvas.save(output_path, "PNG")
    if not ok:
        raise RuntimeError("保存恢复后的 tile 失败: {}".format(output_path))

    return {
        "result_path": output_path,
        "restored_content_rect": [crop_x, crop_y, crop_w, crop_h],
    }


def crop_atlas_to_used_bounds(atlas_pixmap, manifest_tiles, outer_pad=MULTIVIEW_PACK_OUTER_PADDING, bg=DEFAULT_ATLAS_BG):
    if atlas_pixmap is None or atlas_pixmap.isNull():
        raise RuntimeError("crop_atlas_to_used_bounds 输入 atlas 无效")
    if not manifest_tiles:
        raise RuntimeError("crop_atlas_to_used_bounds manifest_tiles 为空")

    min_x = None
    min_y = None
    max_x = None
    max_y = None

    for tile in manifest_tiles:
        x = int(tile.get("x", 0))
        y = int(tile.get("y", 0))
        w = int(tile.get("w", 0))
        h = int(tile.get("h", 0))
        if w <= 0 or h <= 0:
            continue

        if min_x is None or x < min_x:
            min_x = x
        if min_y is None or y < min_y:
            min_y = y
        if max_x is None or x + w > max_x:
            max_x = x + w
        if max_y is None or y + h > max_y:
            max_y = y + h

    if min_x is None or min_y is None or max_x is None or max_y is None:
        raise RuntimeError("无法计算 atlas 使用区域")

    pad = max(0, int(outer_pad))

    crop_x = max(0, min_x - pad)
    crop_y = max(0, min_y - pad)
    crop_r = min(atlas_pixmap.width(), max_x + pad)
    crop_b = min(atlas_pixmap.height(), max_y + pad)

    crop_w = max(1, crop_r - crop_x)
    crop_h = max(1, crop_b - crop_y)

    cropped = atlas_pixmap.copy(crop_x, crop_y, crop_w, crop_h)
    if cropped.isNull():
        raise RuntimeError("atlas 裁切失败")

    shifted_tiles = []
    for tile in manifest_tiles:
        t = dict(tile)
        t["x"] = int(t.get("x", 0)) - crop_x
        t["y"] = int(t.get("y", 0)) - crop_y
        shifted_tiles.append(t)

    return cropped, shifted_tiles, {
        "crop_rect": [crop_x, crop_y, crop_w, crop_h],
        "atlas_size": [crop_w, crop_h],
        "bg": bg,
    }


def _compute_capped_scaled_size(crop_w, crop_h, target_row_h, max_upscale=MULTIVIEW_MAX_UPSCALE):
    crop_w = max(1, int(crop_w))
    crop_h = max(1, int(crop_h))
    target_row_h = max(1.0, float(target_row_h))
    max_upscale = max(0.01, float(max_upscale))

    scale_by_row = target_row_h / float(crop_h)
    scale = min(scale_by_row, max_upscale)

    sw = max(1, int(round(crop_w * scale)))
    sh = max(1, int(round(crop_h * scale)))

    return sw, sh, scale


def build_row_height_layout(crop_records, canvas_w, canvas_h):
    canvas_w = max(1, int(canvas_w))
    canvas_h = max(1, int(canvas_h))

    count = len(crop_records)
    if count <= 0:
        return []

    pad = int(MULTIVIEW_PACK_OUTER_PADDING)
    gap = int(MULTIVIEW_PACK_GAP)

    usable_w = max(1, canvas_w - pad * 2)
    usable_h = max(1, canvas_h - pad * 2)

    if count == 4:
        row_sizes = [2, 2]
    elif count == 6:
        row_sizes = [3, 3]
    else:
        cols = 2 if count <= 4 else 3
        rows = int(math.ceil(float(count) / float(cols)))

        target_row_h = max(1, int((usable_h - gap * (rows - 1)) / max(1, rows)))

        placements = []
        idx = 0
        y = pad

        for r in range(rows):
            row_items = crop_records[idx: idx + cols]
            idx += cols

            scaled_items = []
            row_w = 0
            row_h = 0

            for rec in row_items:
                sw, sh, _ = _compute_capped_scaled_size(
                    rec["crop_w"], rec["crop_h"], target_row_h, max_upscale=MULTIVIEW_MAX_UPSCALE
                )
                scaled_items.append((rec, sw, sh))
                row_w += sw
                row_h = max(row_h, sh)

            row_w += gap * max(0, len(scaled_items) - 1)
            x = pad + int(round((usable_w - row_w) * 0.5))

            for rec, sw, sh in scaled_items:
                draw_y = y + int(round((row_h - sh) * 0.5))
                placements.append({
                    "record_ref": rec,
                    "slot_name": str(rec.get("record", {}).get("slot_name", "") or "").strip().lower(),
                    "cell_rect": [x, y, sw, row_h],
                    "draw_rect": [x, draw_y, sw, sh],
                })
                x += sw + gap

            y += row_h + gap

        return placements

    upper = float(usable_h - gap) / 2.0
    upper = max(1.0, upper)

    def build_candidate_layout(target_row_h):
        scaled = []
        for idx, rec in enumerate(crop_records):
            sw, sh, sc = _compute_capped_scaled_size(
                rec["crop_w"], rec["crop_h"], target_row_h, max_upscale=MULTIVIEW_MAX_UPSCALE
            )
            scaled.append({
                "idx": idx,
                "rec": rec,
                "w": sw,
                "h": sh,
                "scale": sc,
            })

        n = len(scaled)
        first_row_count = row_sizes[0]

        best = None
        best_score = None

        all_indices = list(range(n))

        for comb in combinations(all_indices, first_row_count):
            row1_idx = set(comb)
            row2_idx = [i for i in all_indices if i not in row1_idx]

            row1 = [scaled[i] for i in comb]
            row2 = [scaled[i] for i in row2_idx]

            row1.sort(key=lambda x: x["w"], reverse=True)
            row2.sort(key=lambda x: x["w"], reverse=True)

            row1_w = sum(it["w"] for it in row1) + gap * max(0, len(row1) - 1)
            row2_w = sum(it["w"] for it in row2) + gap * max(0, len(row2) - 1)

            row1_h = max((it["h"] for it in row1), default=1)
            row2_h = max((it["h"] for it in row2), default=1)

            total_h = row1_h + gap + row2_h
            max_row_w = max(row1_w, row2_w)

            fits = (max_row_w <= usable_w and total_h <= usable_h)
            if not fits:
                continue

            width_balance = abs(row1_w - row2_w)
            total_area = max_row_w * total_h
            content_area = sum(it["w"] * it["h"] for it in row1) + sum(it["w"] * it["h"] for it in row2)
            waste = total_area - content_area

            score = (
                width_balance,
                waste,
                total_area
            )

            if best is None or score < best_score:
                best = {
                    "row1": row1,
                    "row2": row2,
                    "row1_w": row1_w,
                    "row2_w": row2_w,
                    "row1_h": row1_h,
                    "row2_h": row2_h,
                    "total_h": total_h,
                    "max_row_w": max_row_w,
                }
                best_score = score

        return best

    lo = 1.0
    hi = upper
    best_layout = None

    for _ in range(28):
        mid = (lo + hi) * 0.5
        candidate = build_candidate_layout(mid)
        if candidate is not None:
            best_layout = candidate
            lo = mid
        else:
            hi = mid

    if best_layout is None:
        best_layout = build_candidate_layout(1.0)

    if best_layout is None:
        return []

    placements = []

    start_y = pad + int(round((usable_h - best_layout["total_h"]) * 0.5))

    y1 = start_y
    x1 = pad + int(round((usable_w - best_layout["row1_w"]) * 0.5))
    for it in best_layout["row1"]:
        draw_y = y1 + int(round((best_layout["row1_h"] - it["h"]) * 0.5))
        placements.append({
            "record_ref": it["rec"],
            "slot_name": str(it["rec"].get("record", {}).get("slot_name", "") or "").strip().lower(),
            "cell_rect": [x1, y1, it["w"], best_layout["row1_h"]],
            "draw_rect": [x1, draw_y, it["w"], it["h"]],
        })
        x1 += it["w"] + gap

    y2 = y1 + best_layout["row1_h"] + gap
    x2 = pad + int(round((usable_w - best_layout["row2_w"]) * 0.5))
    for it in best_layout["row2"]:
        draw_y = y2 + int(round((best_layout["row2_h"] - it["h"]) * 0.5))
        placements.append({
            "record_ref": it["rec"],
            "slot_name": str(it["rec"].get("record", {}).get("slot_name", "") or "").strip().lower(),
            "cell_rect": [x2, y2, it["w"], best_layout["row2_h"]],
            "draw_rect": [x2, draw_y, it["w"], it["h"]],
        })
        x2 += it["w"] + gap

    return placements


def render_row_height_atlas(placements, atlas_w, atlas_h):
    atlas = QtGui.QPixmap(int(atlas_w), int(atlas_h))
    atlas.fill(QtGui.QColor(DEFAULT_ATLAS_BG))

    manifest_tiles = []

    painter = QtGui.QPainter(atlas)
    try:
        for idx, placement in enumerate(placements):
            rec = placement.get("record_ref") or {}
            draw_rect = placement.get("draw_rect") or [0, 0, 1, 1]
            x, y, w, h = [int(v) for v in draw_rect]

            cropped_pixmap = rec.get("cropped_pixmap")
            if cropped_pixmap is None or cropped_pixmap.isNull():
                continue

            scaled_pm = cropped_pixmap.scaled(
                w,
                h,
                QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation
            )
            painter.drawPixmap(x, y, scaled_pm)

            src_rec = rec.get("record") or {}
            crop_meta = rec.get("crop_meta") or {}

            manifest_tiles.append({
                "index": idx,
                "slot_name": src_rec.get("slot_name"),
                "slot_label": src_rec.get("slot_label"),
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "capture_path": src_rec.get("capture_path"),
                "camera_state": src_rec.get("camera_state"),
                "time": src_rec.get("time"),

                "fit_mode": "subject_crop_row_height_layout",
                "source_size": crop_meta.get("original_capture_size"),
                "original_capture_size": crop_meta.get("original_capture_size"),
                "trim_rect_in_capture": crop_meta.get("trim_rect_in_capture"),
                "crop_rect_in_capture": crop_meta.get("crop_rect_in_capture"),
                "tile_content_rect": [0, 0, w, h],
                "tile_output_size": [w, h],
                "packed_rect": [x, y, w, h],
                "cropped_source_size": [rec.get("crop_w", 1), rec.get("crop_h", 1)],
                "bg_rgb": crop_meta.get("bg_rgb"),
                "bg_hex": crop_meta.get("bg_hex", DEFAULT_ATLAS_BG),
            })
    finally:
        painter.end()

    return atlas, manifest_tiles


def build_multiview_atlas(tile_records, atlas_path, tile_size=DEFAULT_MULTI_TILE_SIZE):
    if not tile_records:
        raise RuntimeError("tile_records 为空")

    count = len(tile_records)

    atlas_side = MULTIVIEW_PACK_SIDE_4 if count <= 4 else MULTIVIEW_PACK_SIDE_6
    atlas_side = max(512, int(atlas_side))

    crop_records = []

    for idx, rec in enumerate(tile_records):
        src = load_pixmap_safe(rec["capture_path"])
        src_w = src.width()
        src_h = src.height()
        if src_w <= 0 or src_h <= 0:
            raise RuntimeError("输入截图尺寸无效: {}".format(rec["capture_path"]))

        cropped, crop_meta = crop_subject_from_capture(src)

        crop_w = cropped.width()
        crop_h = cropped.height()
        if crop_w <= 0 or crop_h <= 0:
            raise RuntimeError("主体裁剪结果无效: {}".format(rec["capture_path"]))

        crop_records.append({
            "index": idx,
            "record": rec,
            "cropped_pixmap": cropped,
            "crop_w": crop_w,
            "crop_h": crop_h,
            "crop_meta": crop_meta,
        })

    placements = build_row_height_layout(
        crop_records=crop_records,
        canvas_w=atlas_side,
        canvas_h=atlas_side
    )

    if not placements:
        raise RuntimeError("多视角行高布局失败")

    atlas, manifest_tiles = render_row_height_atlas(
        placements=placements,
        atlas_w=atlas_side,
        atlas_h=atlas_side
    )

    cropped_atlas, shifted_tiles, crop_info = crop_atlas_to_used_bounds(
        atlas_pixmap=atlas,
        manifest_tiles=manifest_tiles,
        outer_pad=MULTIVIEW_PACK_OUTER_PADDING,
        bg=DEFAULT_ATLAS_BG
    )

    ok = cropped_atlas.save(atlas_path, "PNG")
    if not ok:
        raise RuntimeError("保存多视角拼图失败: {}".format(atlas_path))

    layout_mode = "row_height_4" if count <= 4 else "row_height_6"

    manifest = {
        "type": "multiview_manifest",
        "time": now_str_readable(),
        "atlas_path": atlas_path,
        "atlas_size": crop_info.get("atlas_size", [cropped_atlas.width(), cropped_atlas.height()]),
        "atlas_crop_rect_from_pack_canvas": crop_info.get(
            "crop_rect",
            [0, 0, cropped_atlas.width(), cropped_atlas.height()]
        ),
        "tile_width": 0,
        "tile_height": 0,
        "cols": 0,
        "rows": 0,
        "fit_mode": "subject_crop_row_height_layout",
        "layout_mode": layout_mode,
        "tiles": shifted_tiles,
    }
    return manifest


def split_multiview_result_by_manifest(result_image_path, manifest, output_dir):
    ensure_dir(output_dir)

    if not isinstance(manifest, dict):
        raise RuntimeError("manifest 无效")

    image = QtGui.QImage(result_image_path)
    if image.isNull():
        raise RuntimeError("无法读取结果图: {}".format(result_image_path))

    tiles = manifest.get("tiles", [])
    if not tiles:
        raise RuntimeError("manifest 中没有 tiles")

    src_atlas_path = manifest.get("atlas_path", "")
    src_atlas = QtGui.QImage(src_atlas_path) if src_atlas_path and os.path.exists(src_atlas_path) else QtGui.QImage()

    atlas_size = manifest.get("atlas_size", [])
    if len(atlas_size) == 2:
        expected_src_w = int(atlas_size[0])
        expected_src_h = int(atlas_size[1])
    else:
        expected_src_w = image.width()
        expected_src_h = image.height()

    if not src_atlas.isNull():
        src_w = src_atlas.width()
        src_h = src_atlas.height()
    else:
        src_w = expected_src_w
        src_h = expected_src_h

    dst_w = image.width()
    dst_h = image.height()

    if src_w <= 0 or src_h <= 0 or dst_w <= 0 or dst_h <= 0:
        raise RuntimeError("源/目标图尺寸无效")

    scale_x = float(dst_w) / float(src_w)
    scale_y = float(dst_h) / float(src_h)

    out_records = []
    base_name = os.path.splitext(os.path.basename(result_image_path))[0]

    for tile in tiles:
        slot_name = tile.get("slot_name", "tile")

        src_x = int(tile.get("x", 0))
        src_y = int(tile.get("y", 0))
        src_tw = int(tile.get("w", 0))
        src_th = int(tile.get("h", 0))

        x0 = int(round(src_x * scale_x))
        y0 = int(round(src_y * scale_y))
        x1 = int(round((src_x + src_tw) * scale_x))
        y1 = int(round((src_y + src_th) * scale_y))

        x0 = max(0, min(x0, max(dst_w - 1, 0)))
        y0 = max(0, min(y0, max(dst_h - 1, 0)))
        x1 = max(x0 + 1, min(x1, dst_w))
        y1 = max(y0 + 1, min(y1, dst_h))

        sub = image.copy(x0, y0, x1 - x0, y1 - y0)
        if sub.isNull():
            continue

        raw_tile_path = os.path.join(output_dir, "{}_{}_raw.png".format(base_name, slot_name))
        ok = sub.save(raw_tile_path, "PNG")
        if not ok:
            raise RuntimeError("保存原始切图失败: {}".format(raw_tile_path))

        restored_path = os.path.join(output_dir, "{}_{}.png".format(base_name, slot_name))
        restore_info = restore_generated_tile_to_capture_canvas(
            tile_image_or_path=raw_tile_path,
            tile_manifest=tile,
            output_path=restored_path
        )

        out_records.append({
            "slot_name": slot_name,
            "slot_label": tile.get("slot_label", slot_name),
            "result_path": restored_path,
            "raw_tile_path": raw_tile_path,
            "camera_state": tile.get("camera_state"),
            "source_capture_path": tile.get("capture_path"),
            "crop_src_rect": [src_x, src_y, src_tw, src_th],
            "crop_scaled_rect": [x0, y0, x1 - x0, y1 - y0],
            "restored_content_rect": restore_info.get("restored_content_rect"),
        })

    split_manifest_path = os.path.join(output_dir, "{}_split_manifest.json".format(base_name))
    write_json(split_manifest_path, {
        "type": "multiview_split",
        "time": now_str_readable(),
        "source_result": result_image_path,
        "source_manifest": "<embedded_capture_manifest>",
        "source_size": [src_w, src_h],
        "result_size": [dst_w, dst_h],
        "scale_x": scale_x,
        "scale_y": scale_y,
        "tiles": out_records,
    })

    return out_records, split_manifest_path


def split_single_result_by_manifest(result_image_path, manifest, output_path):
    if not isinstance(manifest, dict):
        raise RuntimeError("single_view manifest 无效")

    image = QtGui.QImage(result_image_path)
    if image.isNull():
        raise RuntimeError("无法读取结果图: {}".format(result_image_path))

    output_size = manifest.get("output_size", [])
    content_rect = manifest.get("content_rect", [])

    if len(output_size) != 2 or len(content_rect) != 4:
        raise RuntimeError("single_view manifest 缺少 output_size / content_rect")

    src_w, src_h = int(output_size[0]), int(output_size[1])
    rx, ry, rw, rh = [int(v) for v in content_rect]

    dst_w = image.width()
    dst_h = image.height()

    if src_w <= 0 or src_h <= 0 or dst_w <= 0 or dst_h <= 0:
        raise RuntimeError("结果尺寸无效")

    scale_x = float(dst_w) / float(src_w)
    scale_y = float(dst_h) / float(src_h)

    x0 = int(round(rx * scale_x))
    y0 = int(round(ry * scale_y))
    x1 = int(round((rx + rw) * scale_x))
    y1 = int(round((ry + rh) * scale_y))

    x0 = max(0, min(x0, max(dst_w - 1, 0)))
    y0 = max(0, min(y0, max(dst_h - 1, 0)))
    x1 = max(x0 + 1, min(x1, dst_w))
    y1 = max(y0 + 1, min(y1, dst_h))

    sub = image.copy(x0, y0, x1 - x0, y1 - y0)
    if sub.isNull():
        raise RuntimeError("裁切单视角结果失败")

    ok = sub.save(output_path, "PNG")
    if not ok:
        raise RuntimeError("保存单视角裁切图失败: {}".format(output_path))

    return {
        "result_path": output_path,
        "crop_scaled_rect": [x0, y0, x1 - x0, y1 - y0],
        "source_result_path": result_image_path,
    }


class NanoBananaClient(object):
    def __init__(
        self,
        api_base,
        api_key,
        submit_path=SUBMIT_PATH,
        result_path=RESULT_PATH,
        poll_interval=DEFAULT_POLL_INTERVAL,
        poll_timeout=DEFAULT_POLL_TIMEOUT,
        use_data_url_prefix=False,
        auth_mode="bearer",
    ):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.submit_path = submit_path
        self.result_path = result_path
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.use_data_url_prefix = use_data_url_prefix
        self.auth_mode = auth_mode

    def _headers(self):
        headers = {
            "Content-Type": "application/json"
        }

        api_key = (self.api_key or "").strip()
        if api_key:
            auth_mode = (self.auth_mode or "bearer").strip().lower()
            if auth_mode == "raw":
                headers["Authorization"] = api_key
            else:
                headers["Authorization"] = "Bearer {}".format(api_key)

        return headers

    def image_file_to_base64(self, image_path):
        b64 = base64.b64encode(read_binary(image_path)).decode("utf-8")
        if self.use_data_url_prefix:
            return "data:image/png;base64," + b64
        return b64

    def submit_task_common(self, prompt, model, aspect_ratio, image_size, urls=None, shut_progress=True,
                           cancel_cb=None):
        if cancel_cb and cancel_cb():
            raise RuntimeError("已取消")

        payload = {
            "model": model,
            "prompt": prompt,
            "aspectRatio": aspect_ratio,
            "imageSize": image_size,
            "webHook": "-1",
            "shutProgress": shut_progress
        }

        if urls:
            payload["urls"] = urls

        url = self.api_base + self.submit_path
        _, text, data = http_post_json(url=url, headers=self._headers(), payload=payload, timeout=30)

        if cancel_cb and cancel_cb():
            raise RuntimeError("已取消")

        if not isinstance(data, dict):
            raise RuntimeError("提交接口返回不是 JSON: {}".format(text))
        if data.get("code") != 0:
            raise RuntimeError("提交失败: {}".format(text))

        try:
            task_id = data["data"]["id"]
        except Exception:
            raise RuntimeError("提交成功但缺少 data.id: {}".format(text))

        return task_id

    def submit_task_multi(self, image_paths, prompt, model, aspect_ratio, image_size, shut_progress=True,
                          cancel_cb=None):
        urls = []

        for image_path in (image_paths or []):
            if cancel_cb and cancel_cb():
                raise RuntimeError("已取消")
            urls.append(self.image_file_to_base64(image_path))

        return self.submit_task_common(
            prompt=prompt,
            model=model,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            urls=urls if urls else None,
            shut_progress=shut_progress,
            cancel_cb=cancel_cb
        )

    def generate_from_images(self, image_paths, prompt, model, aspect_ratio, image_size, shut_progress=True,
                             progress_cb=None, cancel_cb=None):
        if not self.api_key:
            raise RuntimeError("API Key 为空")

        task_id = self.submit_task_multi(
            image_paths=image_paths,
            prompt=prompt,
            model=model,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            shut_progress=shut_progress,
            cancel_cb=cancel_cb
        )

        if progress_cb:
            progress_cb("任务已提交，ID={}".format(task_id))

        image_url = self.poll_result_url(task_id, progress_cb=progress_cb, cancel_cb=cancel_cb)

        if progress_cb:
            progress_cb("结果已完成，正在下载图片...")

        return self.download_image(image_url, cancel_cb=cancel_cb)

    def submit_task(self, image_path, prompt, model, aspect_ratio, image_size, shut_progress=True, cancel_cb=None):
        image_b64 = self.image_file_to_base64(image_path)
        return self.submit_task_common(
            prompt=prompt,
            model=model,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            urls=[image_b64],
            shut_progress=shut_progress,
            cancel_cb=cancel_cb
        )

    def query_result(self, task_id, cancel_cb=None):
        if cancel_cb and cancel_cb():
            raise RuntimeError("已取消")

        url = self.api_base + self.result_path
        payload = {"id": task_id}
        _, text, data = http_post_json(url=url, headers=self._headers(), payload=payload, timeout=15)

        if cancel_cb and cancel_cb():
            raise RuntimeError("已取消")

        if not isinstance(data, dict):
            raise RuntimeError("结果接口返回不是 JSON: {}".format(text))

        return data

    def poll_result_url(self, task_id, progress_cb=None, cancel_cb=None):
        start_time = time.time()
        last_resp = None
        transient_error_count = 0
        max_transient_errors = 8

        while True:
            if cancel_cb and cancel_cb():
                raise RuntimeError("已取消")

            elapsed = time.time() - start_time
            if elapsed > self.poll_timeout:
                raise TimeoutError(
                    "轮询超时 {} 秒，最后响应: {}".format(
                        self.poll_timeout,
                        json.dumps(last_resp, ensure_ascii=False) if last_resp else "None"
                    )
                )

            try:
                data = self.query_result(task_id, cancel_cb=cancel_cb)
                last_resp = data
                transient_error_count = 0
            except Exception as e:
                transient_error_count += 1
                msg = str(e)

                is_transient = (
                    "UNEXPECTED_EOF_WHILE_READING" in msg or
                    "SSLEOFError" in msg or
                    "URLError" in msg or
                    "timed out" in msg.lower() or
                    "timeout" in msg.lower() or
                    "connection reset" in msg.lower()
                )

                if not is_transient or transient_error_count > max_transient_errors:
                    raise RuntimeError("查询结果失败（已重试{}次）: {}".format(transient_error_count - 1, e))

                if progress_cb:
                    progress_cb("结果轮询网络波动，正在重试({}/{})...".format(
                        transient_error_count, max_transient_errors
                    ))

                wait_left = min(2.0, self.poll_interval)
                while wait_left > 0:
                    if cancel_cb and cancel_cb():
                        raise RuntimeError("已取消")
                    step = min(0.2, wait_left)
                    time.sleep(step)
                    wait_left -= step
                continue

            code = data.get("code")
            if code == -22:
                raise RuntimeError("任务不存在: {}".format(task_id))
            if code != 0:
                raise RuntimeError("查询失败: {}".format(json.dumps(data, ensure_ascii=False)))

            result = data.get("data", {}) or {}
            status = str(result.get("status", "")).strip().lower()
            progress = result.get("progress", 0)

            if progress_cb:
                progress_cb("任务中... status={} progress={}%".format(status or "unknown", progress))

            if status == "succeeded":
                results = result.get("results", [])
                if not results:
                    raise RuntimeError("任务成功，但 results 为空")
                image_url = results[0].get("url")
                if not image_url:
                    raise RuntimeError("任务成功，但 results[0].url 为空")
                return image_url

            if status == "failed":
                failure_reason = result.get("failure_reason", "")
                error = result.get("error", "")
                raise RuntimeError("生成失败: failure_reason={}, error={}".format(failure_reason, error))

            wait_left = self.poll_interval
            while wait_left > 0:
                if cancel_cb and cancel_cb():
                    raise RuntimeError("已取消")
                step = min(0.2, wait_left)
                time.sleep(step)
                wait_left -= step

    def download_image(self, image_url, cancel_cb=None):
        if cancel_cb and cancel_cb():
            raise RuntimeError("已取消")
        return http_get_bytes(image_url, timeout=30)

    def generate_from_prompt(self, prompt, model, aspect_ratio, image_size, shut_progress=True, progress_cb=None,
                             cancel_cb=None):
        if not self.api_key:
            raise RuntimeError("API Key 为空")

        task_id = self.submit_task_common(
            prompt=prompt,
            model=model,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            urls=None,
            shut_progress=shut_progress,
            cancel_cb=cancel_cb
        )

        if progress_cb:
            progress_cb("任务已提交，ID={}".format(task_id))

        image_url = self.poll_result_url(task_id, progress_cb=progress_cb, cancel_cb=cancel_cb)

        if progress_cb:
            progress_cb("结果已完成，正在下载图片...")

        return self.download_image(image_url, cancel_cb=cancel_cb)

    def generate_from_image(self, image_path, prompt, model, aspect_ratio, image_size, shut_progress=True, progress_cb=None, cancel_cb=None):
        if not self.api_key:
            raise RuntimeError("API Key 为空")

        task_id = self.submit_task(
            image_path=image_path,
            prompt=prompt,
            model=model,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            shut_progress=shut_progress,
            cancel_cb=cancel_cb
        )

        if progress_cb:
            progress_cb("任务已提交，ID={}".format(task_id))

        image_url = self.poll_result_url(task_id, progress_cb=progress_cb, cancel_cb=cancel_cb)

        if progress_cb:
            progress_cb("结果已完成，正在下载图片...")

        return self.download_image(image_url, cancel_cb=cancel_cb)


class RunningHubClient(object):
    def __init__(
        self,
        api_base,
        api_key,
        submit_path=RUNNINGHUB_DEFAULT_SUBMIT_PATH,
        result_path=RUNNINGHUB_RESULT_PATH,
        upload_path=RUNNINGHUB_UPLOAD_PATH,
        poll_interval=DEFAULT_POLL_INTERVAL,
        poll_timeout=DEFAULT_POLL_TIMEOUT,
        auth_mode="bearer",
        upload_mode=RUNNINGHUB_UPLOAD_DATA_URI,
    ):
        self.api_base = (api_base or RUNNINGHUB_API_BASE).rstrip("/")
        self.api_key = api_key
        self.submit_path = submit_path
        self.result_path = result_path
        self.upload_path = upload_path
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.auth_mode = auth_mode
        self.upload_mode = upload_mode

    def _headers(self, include_content_type=True):
        headers = {}
        if include_content_type:
            headers["Content-Type"] = "application/json"

        api_key = (self.api_key or "").strip()
        if api_key:
            auth_mode = (self.auth_mode or "bearer").strip().lower()
            if auth_mode == "raw":
                headers["Authorization"] = api_key
            else:
                headers["Authorization"] = "Bearer {}".format(api_key)
        return headers

    def image_file_to_data_uri(self, image_path):
        data = read_binary(image_path)
        ext = os.path.splitext(image_path)[1].lower()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }.get(ext, "application/octet-stream")
        b64 = base64.b64encode(data).decode("utf-8")
        return "data:{};base64,{}".format(mime, b64)

    def upload_binary_and_get_url(self, image_path):
        url = self.api_base + self.upload_path
        filename = os.path.basename(image_path)
        ext = os.path.splitext(filename)[1].lower()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }.get(ext, "application/octet-stream")

        _, text, data = http_post_multipart(
            url=url,
            headers=self._headers(include_content_type=False),
            files=[{
                "name": "file",
                "filename": filename,
                "content": read_binary(image_path),
                "content_type": mime,
            }],
            timeout=60
        )

        if not isinstance(data, dict):
            raise RuntimeError("RunningHub 上传返回不是 JSON: {}".format(text))

        if data.get("code") != 0:
            raise RuntimeError("RunningHub 上传失败: {}".format(text))

        data_obj = data.get("data") or {}
        download_url = str(data_obj.get("download_url", "") or "").strip()
        if not download_url:
            raise RuntimeError("RunningHub 上传成功但缺少 data.download_url: {}".format(text))

        return download_url

    def _map_aspect_ratio(self, aspect_ratio):
        text = str(aspect_ratio or "").strip().lower()
        if not text:
            return "auto"

        if text == "auto":
            return "auto"

        mapping = {
            "1:1": "1:1",
            "16:9": "16:9",
            "9:16": "9:16",
            "4:3": "4:3",
            "3:4": "3:4",
            "3:2": "3:2",
            "2:3": "2:3",
            "5:4": "5:4",
            "4:5": "4:5",
            "21:9": "21:9",
            "1:4": "1:4",
            "4:1": "4:1",
            "1:8": "1:8",
            "8:1": "8:1",
        }
        return mapping.get(text, "auto")

    def _map_resolution(self, image_size):
        text = str(image_size or "").strip().lower()
        mapping = {
            "1k": "1k",
            "2k": "2k",
            "4k": "4k",
        }
        return mapping.get(text, "1k")

    def build_image_url_value(self, image_path):
        mode = (self.upload_mode or RUNNINGHUB_UPLOAD_DATA_URI).strip().lower()
        if mode == RUNNINGHUB_UPLOAD_BINARY:
            return self.upload_binary_and_get_url(image_path)
        return self.image_file_to_data_uri(image_path)

    def submit_task_multi(self, image_paths, prompt, model, aspect_ratio, image_size, shut_progress=True,
                          cancel_cb=None):
        if cancel_cb and cancel_cb():
            raise RuntimeError("已取消")

        image_urls = []
        for image_path in (image_paths or []):
            if cancel_cb and cancel_cb():
                raise RuntimeError("已取消")
            image_urls.append(self.build_image_url_value(image_path))

        return self.submit_task_common(
            prompt=prompt,
            model=model,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            image_urls=image_urls if image_urls else None,
            shut_progress=shut_progress,
            cancel_cb=cancel_cb
        )

    def generate_from_images(self, image_paths, prompt, model, aspect_ratio, image_size, shut_progress=True,
                             progress_cb=None, cancel_cb=None):
        if not self.api_key:
            raise RuntimeError("API Key 为空")

        task_id = self.submit_task_multi(
            image_paths=image_paths,
            prompt=prompt,
            model=model,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            shut_progress=shut_progress,
            cancel_cb=cancel_cb
        )

        if progress_cb:
            progress_cb("任务已提交，ID={}".format(task_id))

        image_url = self.poll_result_url(task_id, progress_cb=progress_cb, cancel_cb=cancel_cb)

        if progress_cb:
            progress_cb("结果已完成，正在下载图片...")

        return self.download_image(image_url, cancel_cb=cancel_cb)

    def submit_task_common(self, prompt, model, aspect_ratio, image_size, image_urls=None, shut_progress=True,
                           cancel_cb=None):
        if cancel_cb and cancel_cb():
            raise RuntimeError("已取消")

        payload = {
            "prompt": prompt,
            "aspectRatio": self._map_aspect_ratio(aspect_ratio),
            "resolution": self._map_resolution(image_size),
        }

        if image_urls:
            payload["imageUrls"] = image_urls

        url = self.api_base + self.submit_path
        _, text, data = http_post_json(
            url=url,
            headers=self._headers(include_content_type=True),
            payload=payload,
            timeout=60
        )

        if cancel_cb and cancel_cb():
            raise RuntimeError("已取消")

        if not isinstance(data, dict):
            raise RuntimeError("RunningHub 提交接口返回不是 JSON: {}".format(text))

        task_id = str(data.get("taskId", "") or "").strip()
        if not task_id:
            raise RuntimeError("RunningHub 提交成功但缺少 taskId: {}".format(text))

        return task_id

    def submit_task(self, image_path, prompt, model, aspect_ratio, image_size, shut_progress=True, cancel_cb=None):
        if cancel_cb and cancel_cb():
            raise RuntimeError("已取消")

        image_value = self.build_image_url_value(image_path)

        return self.submit_task_common(
            prompt=prompt,
            model=model,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            image_urls=[image_value],
            shut_progress=shut_progress,
            cancel_cb=cancel_cb
        )

    def query_result(self, task_id, cancel_cb=None):
        if cancel_cb and cancel_cb():
            raise RuntimeError("已取消")

        url = self.api_base + self.result_path
        payload = {"taskId": task_id}

        _, text, data = http_post_json(
            url=url,
            headers=self._headers(include_content_type=True),
            payload=payload,
            timeout=20
        )

        if cancel_cb and cancel_cb():
            raise RuntimeError("已取消")

        if not isinstance(data, dict):
            raise RuntimeError("RunningHub 结果接口返回不是 JSON: {}".format(text))

        return data

    def poll_result_url(self, task_id, progress_cb=None, cancel_cb=None):
        start_time = time.time()
        last_resp = None
        transient_error_count = 0
        max_transient_errors = 8

        while True:
            if cancel_cb and cancel_cb():
                raise RuntimeError("已取消")

            elapsed = time.time() - start_time
            if elapsed > self.poll_timeout:
                raise TimeoutError(
                    "轮询超时 {} 秒，最后响应: {}".format(
                        self.poll_timeout,
                        json.dumps(last_resp, ensure_ascii=False) if last_resp else "None"
                    )
                )

            try:
                data = self.query_result(task_id, cancel_cb=cancel_cb)
                last_resp = data
                transient_error_count = 0
            except Exception as e:
                transient_error_count += 1
                msg = str(e)
                is_transient = (
                    "UNEXPECTED_EOF_WHILE_READING" in msg or
                    "SSLEOFError" in msg or
                    "URLError" in msg or
                    "timed out" in msg.lower() or
                    "timeout" in msg.lower() or
                    "connection reset" in msg.lower()
                )

                if not is_transient or transient_error_count > max_transient_errors:
                    raise RuntimeError("查询结果失败（已重试{}次）: {}".format(transient_error_count - 1, e))

                if progress_cb:
                    progress_cb("结果轮询网络波动，正在重试({}/{})...".format(
                        transient_error_count, max_transient_errors
                    ))

                wait_left = min(2.0, self.poll_interval)
                while wait_left > 0:
                    if cancel_cb and cancel_cb():
                        raise RuntimeError("已取消")
                    step = min(0.2, wait_left)
                    time.sleep(step)
                    wait_left -= step
                continue

            status = str(data.get("status", "") or "").strip().upper()

            if progress_cb:
                progress_cb("任务中... status={}".format(status or "UNKNOWN"))

            if status == "SUCCESS":
                results = data.get("results", [])
                if not results:
                    raise RuntimeError("任务成功，但 results 为空")
                first = results[0] or {}
                image_url = first.get("url")
                if not image_url:
                    raise RuntimeError("任务成功，但 results[0].url 为空")
                return image_url

            if status == "FAILED":
                error_code = data.get("errorCode", "")
                error_message = data.get("errorMessage", "")
                failed_reason = data.get("failedReason", "")
                raise RuntimeError(
                    "生成失败: errorCode={}, errorMessage={}, failedReason={}".format(
                        error_code, error_message, failed_reason
                    )
                )

            wait_left = self.poll_interval
            while wait_left > 0:
                if cancel_cb and cancel_cb():
                    raise RuntimeError("已取消")
                step = min(0.2, wait_left)
                time.sleep(step)
                wait_left -= step

    def download_image(self, image_url, cancel_cb=None):
        if cancel_cb and cancel_cb():
            raise RuntimeError("已取消")
        return http_get_bytes(image_url, timeout=60)

    def generate_from_image(self, image_path, prompt, model, aspect_ratio, image_size, shut_progress=True, progress_cb=None, cancel_cb=None):
        if not self.api_key:
            raise RuntimeError("API Key 为空")

        task_id = self.submit_task(
            image_path=image_path,
            prompt=prompt,
            model=model,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            shut_progress=shut_progress,
            cancel_cb=cancel_cb
        )

        if progress_cb:
            progress_cb("任务已提交，ID={}".format(task_id))

        image_url = self.poll_result_url(task_id, progress_cb=progress_cb, cancel_cb=cancel_cb)

        if progress_cb:
            progress_cb("结果已完成，正在下载图片...")

        return self.download_image(image_url, cancel_cb=cancel_cb)


def build_image_client(settings_data):
    s = merge_plugin_settings(settings_data)
    provider = s.get("provider", PROVIDER_GRSAI)

    if provider == PROVIDER_GRSAI:
        return NanoBananaClient(
            api_base=s["api_base"],
            api_key=s["api_key"],
            submit_path=s["submit_path"],
            result_path=s["result_path"],
            poll_interval=s["poll_interval"],
            poll_timeout=s["poll_timeout"],
            use_data_url_prefix=s["use_data_url_prefix"],
            auth_mode=s["auth_mode"],
        )

    if provider == PROVIDER_RUNNINGHUB:
        return RunningHubClient(
            api_base=s["api_base"],
            api_key=s["api_key"],
            submit_path=s["submit_path"],
            result_path=s["result_path"],
            upload_path=s["runninghub_upload_path"],
            poll_interval=s["poll_interval"],
            poll_timeout=s["poll_timeout"],
            auth_mode=s["auth_mode"],
            upload_mode=s["runninghub_upload_mode"],
        )

    raise RuntimeError("不支持的平台类型: {}".format(provider))


class PreviewImageLabel(QtWidgets.QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Ignored
        )
        self.setMinimumSize(100, 100)
        self._source_pixmap = None

    def set_source_pixmap(self, pixmap):
        self._source_pixmap = pixmap
        self.refresh()

    def clear_source_pixmap(self):
        self._source_pixmap = None
        self.clear()

    def refresh(self):
        if self._source_pixmap is None or self._source_pixmap.isNull():
            self.clear()
            return

        target_size = self.size()
        if target_size.width() < 10 or target_size.height() < 10:
            return

        scaled = self._source_pixmap.scaled(
            target_size,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation
        )
        self.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh()

    def sizeHint(self):
        return QtCore.QSize(800, 600)

    def minimumSizeHint(self):
        return QtCore.QSize(200, 160)


class ThumbIconOnlyDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, thumb_size, parent=None):
        super().__init__(parent)
        self.thumb_size = thumb_size

    def paint(self, painter, option, index):
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        painter.save()
        try:
            opt.state = opt.state & ~QtWidgets.QStyle.StateFlag.State_HasFocus

            item_rect = opt.rect

            icon_w = min(self.thumb_size.width(), item_rect.width())
            icon_h = min(self.thumb_size.height(), item_rect.height())
            icon_x = item_rect.x() + int((item_rect.width() - icon_w) / 2)
            icon_y = item_rect.y() + 4
            icon_rect = QtCore.QRect(icon_x, icon_y, icon_w, icon_h)

            if opt.state & QtWidgets.QStyle.StateFlag.State_Selected:
                sel_rect = icon_rect.adjusted(-4, -4, 4, 4)
                painter.fillRect(sel_rect, QtGui.QColor("#3d5a80"))
                painter.setPen(QtGui.QPen(QtGui.QColor("#6fa8dc")))
                painter.drawRect(sel_rect.adjusted(0, 0, -1, -1))

            icon = index.data(QtCore.Qt.ItemDataRole.DecorationRole)
            if isinstance(icon, QtGui.QIcon) and not icon.isNull():
                pixmap = icon.pixmap(self.thumb_size)
                painter.drawPixmap(icon_x, icon_y, pixmap)

        finally:
            painter.restore()

    def sizeHint(self, option, index):
        return QtCore.QSize(THUMB_GRID_W, THUMB_GRID_H)


class ThumbListWidget(QtWidgets.QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.enable_file_drag = False
        self.drag_use_result_path = True

    def _icon_hit_rect(self, item):
        rect = self.visualItemRect(item)
        icon_size = self.iconSize()

        icon_w = min(icon_size.width(), rect.width())
        icon_h = min(icon_size.height(), rect.height())

        x = rect.x() + int((rect.width() - icon_w) / 2)
        y = rect.y() + 4

        return QtCore.QRect(x, y, icon_w, icon_h)

    def item_at_icon_pos(self, pos):
        item = self.itemAt(pos)
        if item is None:
            return None
        if not self._icon_hit_rect(item).contains(pos):
            return None
        return item

    def mousePressEvent(self, event):
        item = self.item_at_icon_pos(event.pos())
        if item is None:
            self.clearSelection()
            self.setCurrentItem(None)
            return
        super().mousePressEvent(event)

    def _drag_exec(self, drag):
        return drag.exec(QtCore.Qt.DropAction.CopyAction)

    def startDrag(self, supportedActions):
        if not self.enable_file_drag:
            return

        item = self.currentItem()
        if item is None:
            return

        record = item.data(QtCore.Qt.ItemDataRole.UserRole) or {}

        if self.drag_use_result_path:
            path = record.get("result_path") or record.get("capture_path")
        else:
            path = record.get("capture_path") or record.get("result_path")

        if not path or not os.path.exists(path):
            return

        resource_url = None
        if sp_resource is not None:
            try:
                usage = None
                usage_members = getattr(sp_resource.Usage, "__members__", {})
                for name in ["Texture", "Textures", "Bitmap", "Image"]:
                    if name in usage_members:
                        usage = getattr(sp_resource.Usage, name)
                        break
                if usage is None:
                    for name in usage_members.keys():
                        low = name.lower()
                        if "texture" in low or "bitmap" in low or "image" in low:
                            usage = getattr(sp_resource.Usage, name)
                            break

                if usage is not None:
                    res = sp_resource.import_project_resource(
                        file_path=path,
                        resource_usage=usage,
                        name=os.path.splitext(os.path.basename(path))[0],
                        group="AIViewToPaint"
                    )
                    rid = res.identifier()
                    resource_url = str(rid.url())

            except Exception as e:
                print("[ThumbListWidget] import resource failed: {}".format(e))

        mime = QtCore.QMimeData()

        if resource_url:
            mime.setUrls([QtCore.QUrl(resource_url)])
            mime.setText(resource_url)
            mime.setData(
                "application/x-substance-resource-url",
                resource_url.encode("utf-8")
            )
        else:
            mime.setUrls([QtCore.QUrl.fromLocalFile(path)])
            mime.setText(path)

        drag = QtGui.QDrag(self)
        drag.setMimeData(mime)

        icon = item.icon()
        if isinstance(icon, QtGui.QIcon) and not icon.isNull():
            drag.setPixmap(icon.pixmap(self.iconSize()))

        self._drag_exec(drag)


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, settings_data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(560, 380)

        self.settings_data = merge_plugin_settings(settings_data)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        tip = QtWidgets.QLabel("配置API接口。")
        tip.setStyleSheet("color:#cfcfcf;")
        tip.setWordWrap(True)
        root.addWidget(tip)

        self.form = QtWidgets.QFormLayout()
        self.form.setHorizontalSpacing(8)
        self.form.setVerticalSpacing(8)
        root.addLayout(self.form)

        self.provider_combo = QtWidgets.QComboBox()
        self.provider_combo.addItem("GRSAI", PROVIDER_GRSAI)
        self.provider_combo.addItem("RunningHub", PROVIDER_RUNNINGHUB)
        idx = self.provider_combo.findData(self.settings_data.get("provider", PROVIDER_GRSAI))
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        self.form.addRow("平台类型", self.provider_combo)

        self.api_base_edit = QtWidgets.QLineEdit(self.settings_data.get("api_base", ""))
        self.form.addRow("API Base", self.api_base_edit)

        self.api_key_edit = QtWidgets.QLineEdit(self.settings_data.get("api_key", ""))
        self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.form.addRow("API Key", self.api_key_edit)

        self.auth_mode_combo = QtWidgets.QComboBox()
        self.auth_mode_combo.addItem("Bearer", "bearer")
        self.auth_mode_combo.addItem("Raw Key", "raw")
        idx = self.auth_mode_combo.findData(self.settings_data.get("auth_mode", "bearer"))
        if idx >= 0:
            self.auth_mode_combo.setCurrentIndex(idx)
        self.form.addRow("鉴权方式", self.auth_mode_combo)

        self.model_edit = QtWidgets.QLineEdit(self.settings_data.get("default_model", DEFAULT_MODEL))
        self.form.addRow("默认模型", self.model_edit)

        self.output_dir_edit = QtWidgets.QLineEdit(self.settings_data.get("output_dir", DEFAULT_OUTPUT_DIR))
        self.output_dir_btn = QtWidgets.QPushButton("选择目录")
        self.output_dir_btn.setFixedWidth(90)
        self.output_dir_btn.clicked.connect(self.on_pick_output_dir)

        output_row = QtWidgets.QWidget()
        output_layout = QtWidgets.QHBoxLayout(output_row)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(6)
        output_layout.addWidget(self.output_dir_edit, 1)
        output_layout.addWidget(self.output_dir_btn, 0)
        self.form.addRow("输出目录", output_row)

        self.submit_path_edit = QtWidgets.QLineEdit(self.settings_data.get("submit_path", SUBMIT_PATH))
        self.result_path_edit = QtWidgets.QLineEdit(self.settings_data.get("result_path", RESULT_PATH))
        self.form.addRow("提交路径", self.submit_path_edit)
        self.form.addRow("结果路径", self.result_path_edit)

        self.runninghub_upload_path_edit = QtWidgets.QLineEdit(
            self.settings_data.get("runninghub_upload_path", RUNNINGHUB_UPLOAD_PATH)
        )
        self.form.addRow("上传路径", self.runninghub_upload_path_edit)

        self.runninghub_upload_mode_combo = QtWidgets.QComboBox()
        self.runninghub_upload_mode_combo.addItem("Base64 Data URI", RUNNINGHUB_UPLOAD_DATA_URI)
        self.runninghub_upload_mode_combo.addItem("先上传文件再传URL", RUNNINGHUB_UPLOAD_BINARY)
        idx = self.runninghub_upload_mode_combo.findData(
            self.settings_data.get("runninghub_upload_mode", RUNNINGHUB_UPLOAD_DATA_URI)
        )
        if idx >= 0:
            self.runninghub_upload_mode_combo.setCurrentIndex(idx)
        self.form.addRow("上传方式", self.runninghub_upload_mode_combo)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

        root.addStretch(1)

        self._last_provider_for_key_switch = None
        self.provider_combo.currentIndexChanged.connect(self.on_provider_changed)
        self.on_provider_changed()

    def on_provider_changed(self):
        old_provider = getattr(self, "_last_provider_for_key_switch", None)
        new_provider = self.provider_combo.currentData()

        provider_api_keys = dict(self.settings_data.get("provider_api_keys", {}) or {})

        if old_provider:
            provider_api_keys[old_provider] = self.api_key_edit.text().strip()

        self.settings_data["provider_api_keys"] = provider_api_keys
        self._last_provider_for_key_switch = new_provider

        provider = new_provider
        preset = PROVIDER_PRESETS.get(provider, {})
        is_runninghub = (provider == PROVIDER_RUNNINGHUB)

        submit_label = self.form.labelForField(self.submit_path_edit)
        result_label = self.form.labelForField(self.result_path_edit)
        upload_label = self.form.labelForField(self.runninghub_upload_path_edit)
        upload_mode_label = self.form.labelForField(self.runninghub_upload_mode_combo)

        show_submit_result = is_runninghub
        self.submit_path_edit.setVisible(show_submit_result)
        self.result_path_edit.setVisible(show_submit_result)

        if submit_label is not None:
            submit_label.setVisible(show_submit_result)
        if result_label is not None:
            result_label.setVisible(show_submit_result)

        self.runninghub_upload_path_edit.setVisible(is_runninghub)
        self.runninghub_upload_mode_combo.setVisible(is_runninghub)

        if upload_label is not None:
            upload_label.setVisible(is_runninghub)
        if upload_mode_label is not None:
            upload_mode_label.setVisible(is_runninghub)

        provider_key = provider_api_keys.get(provider, "")
        self.api_key_edit.setText(provider_key)

        if provider == PROVIDER_GRSAI:
            self.api_base_edit.setText(preset.get("api_base", ""))
            self.submit_path_edit.setText(preset.get("submit_path", SUBMIT_PATH))
            self.result_path_edit.setText(preset.get("result_path", RESULT_PATH))

            idx = self.auth_mode_combo.findData(preset.get("auth_mode", "bearer"))
            if idx >= 0:
                self.auth_mode_combo.setCurrentIndex(idx)

        elif provider == PROVIDER_RUNNINGHUB:
            self.api_base_edit.setText(preset.get("api_base", RUNNINGHUB_API_BASE))
            if not self.submit_path_edit.text().strip():
                self.submit_path_edit.setText(preset.get("submit_path", RUNNINGHUB_DEFAULT_SUBMIT_PATH))
            self.result_path_edit.setText(preset.get("result_path", RUNNINGHUB_RESULT_PATH))
            self.runninghub_upload_path_edit.setText(preset.get("upload_path", RUNNINGHUB_UPLOAD_PATH))

            idx = self.auth_mode_combo.findData(preset.get("auth_mode", "bearer"))
            if idx >= 0:
                self.auth_mode_combo.setCurrentIndex(idx)

            idx = self.runninghub_upload_mode_combo.findData(
                self.settings_data.get("runninghub_upload_mode", preset.get("upload_mode", RUNNINGHUB_UPLOAD_DATA_URI))
            )
            if idx >= 0:
                self.runninghub_upload_mode_combo.setCurrentIndex(idx)

    def on_pick_output_dir(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "选择输出目录",
            self.output_dir_edit.text().strip() or DEFAULT_OUTPUT_DIR
        )
        if path:
            self.output_dir_edit.setText(path)

    def get_settings(self):
        provider = self.provider_combo.currentData()
        preset = PROVIDER_PRESETS.get(provider, {})

        provider_api_keys = dict(self.settings_data.get("provider_api_keys", {}) or {})
        provider_api_keys[provider] = self.api_key_edit.text().strip()

        return merge_plugin_settings({
            "provider": provider,
            "api_base": self.api_base_edit.text().strip(),
            "api_key": self.api_key_edit.text().strip(),
            "provider_api_keys": provider_api_keys,
            "auth_mode": self.auth_mode_combo.currentData(),
            "submit_path": self.submit_path_edit.text().strip() if provider == PROVIDER_RUNNINGHUB else preset.get(
                "submit_path", SUBMIT_PATH),
            "result_path": self.result_path_edit.text().strip() if provider == PROVIDER_RUNNINGHUB else preset.get(
                "result_path", RESULT_PATH),
            "runninghub_upload_path": self.runninghub_upload_path_edit.text().strip() if provider == PROVIDER_RUNNINGHUB else preset.get(
                "upload_path", RUNNINGHUB_UPLOAD_PATH),
            "runninghub_upload_mode": self.runninghub_upload_mode_combo.currentData() if provider == PROVIDER_RUNNINGHUB else preset.get(
                "upload_mode", RUNNINGHUB_UPLOAD_DATA_URI),
            "default_model": self.model_edit.text().strip(),
            "output_dir": self.output_dir_edit.text().strip(),
        })


class QLabelPreviewBox(QtWidgets.QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 320)
        self.setStyleSheet("background:#1f1f1f; border:1px solid #555;")
        self._pixmap = None
        self.setText("预览")

    def set_pixmap(self, pixmap):
        self._pixmap = pixmap
        self.refresh()

    def clear_preview(self):
        self._pixmap = None
        self.setPixmap(QtGui.QPixmap())
        self.setText("预览")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh()

    def refresh(self):
        if self._pixmap is None or self._pixmap.isNull():
            return

        scaled = self._pixmap.scaled(
            self.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation
        )
        self.setPixmap(scaled)
        self.setText("")


class ReferenceImagesDialog(QtWidgets.QDialog):
    def __init__(self, image_paths=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("参考图管理")
        self.resize(760, 520)

        self.image_paths = list(image_paths or [])

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        top_tip = QtWidgets.QLabel("可添加多张参考图，生成时将按顺序提交。")
        top_tip.setStyleSheet("color:#cfcfcf;")
        top_tip.setWordWrap(True)
        root.addWidget(top_tip)

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(10)
        root.addLayout(body, 1)

        left_col = QtWidgets.QVBoxLayout()
        left_col.setSpacing(8)
        body.addLayout(left_col, 0)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setMinimumWidth(300)
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        left_col.addWidget(self.list_widget, 1)

        btn_row1 = QtWidgets.QHBoxLayout()
        btn_row1.setSpacing(6)
        left_col.addLayout(btn_row1)

        self.add_btn = QtWidgets.QPushButton("添加")
        self.remove_btn = QtWidgets.QPushButton("删除")
        btn_row1.addWidget(self.add_btn)
        btn_row1.addWidget(self.remove_btn)

        btn_row2 = QtWidgets.QHBoxLayout()
        btn_row2.setSpacing(6)
        left_col.addLayout(btn_row2)

        self.clear_btn = QtWidgets.QPushButton("清空")
        self.open_btn = QtWidgets.QPushButton("打开文件")
        btn_row2.addWidget(self.clear_btn)
        btn_row2.addWidget(self.open_btn)

        right_col = QtWidgets.QVBoxLayout()
        right_col.setSpacing(8)
        body.addLayout(right_col, 1)

        self.info_label = QtWidgets.QLabel("未选择参考图")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color:#cfcfcf;")
        right_col.addWidget(self.info_label, 0)

        self.preview_label = QLabelPreviewBox()
        right_col.addWidget(self.preview_label, 1)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        root.addWidget(btn_box)

        self.add_btn.clicked.connect(self.on_add_clicked)
        self.remove_btn.clicked.connect(self.on_remove_clicked)
        self.clear_btn.clicked.connect(self.on_clear_clicked)
        self.open_btn.clicked.connect(self.on_open_clicked)
        self.list_widget.currentItemChanged.connect(self.on_current_item_changed)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)

        self.refresh_list()

    def refresh_list(self):
        self.list_widget.clear()

        for i, path in enumerate(self.image_paths):
            label = "参考图{}".format(i + 1)
            text = "{}  |  {}".format(label, os.path.basename(path))
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        else:
            self.preview_label.clear_preview()
            self.info_label.setText("未选择参考图")

    def on_add_clicked(self):
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "选择参考图",
            os.path.expanduser("~/Pictures"),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not files:
            return

        existing = set(normalize_path_str(p) for p in self.image_paths)

        for f in files:
            nf = normalize_path_str(f)
            if nf not in existing:
                self.image_paths.append(f)
                existing.add(nf)

        self.refresh_list()

    def on_remove_clicked(self):
        item = self.list_widget.currentItem()
        if item is None:
            return

        path = item.data(QtCore.Qt.ItemDataRole.UserRole)
        target = normalize_path_str(path)
        self.image_paths = [p for p in self.image_paths if normalize_path_str(p) != target]
        self.refresh_list()

    def on_clear_clicked(self):
        self.image_paths = []
        self.refresh_list()

    def on_open_clicked(self):
        item = self.list_widget.currentItem()
        if item is None:
            return

        path = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if path and os.path.exists(path):
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))

    def on_current_item_changed(self, current, previous):
        if current is None:
            self.preview_label.clear_preview()
            self.info_label.setText("未选择参考图")
            return

        path = current.data(QtCore.Qt.ItemDataRole.UserRole)
        self.info_label.setText("路径: {}".format(path))

        pixmap = QtGui.QPixmap(path)
        if pixmap.isNull():
            self.preview_label.clear_preview()
            self.info_label.setText("图片无法加载: {}".format(path))
            return

        self.preview_label.set_pixmap(pixmap)

    def get_image_paths(self):
        return list(self.image_paths)


class AIGenPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(PLUGIN_TITLE)
        self.setObjectName(PANEL_OBJECT_NAME)

        self.settings_data = load_plugin_settings()
        self.client = self.build_client_from_settings(self.settings_data)

        self.last_result_path = None
        self.current_preview_record = None
        self.pending_job_context = None
        self.pending_apply_payload = None
        self._suppress_tab_clear = False
        self.reference_image_paths = []
        self._last_progress_log_text = ""

        self.gen_queue = py_queue.Queue()
        self.gen_thread = None
        self.gen_running = False
        self.gen_cancel_requested = False

        self.thumb_size = QtCore.QSize(THUMB_SIZE, THUMB_SIZE)
        self.thumb_grid_size = QtCore.QSize(THUMB_GRID_W, THUMB_GRID_H)

        self.setMinimumSize(360, 320)
        self.resize(460, 860)

        self._build_ui()
        self.apply_settings_to_ui()
        self.refresh_reference_images_button_text()

        self.gen_poll_timer = QtCore.QTimer(self)
        self.gen_poll_timer.setInterval(150)
        self.gen_poll_timer.timeout.connect(self.poll_generate_queue)

        self.clear_preview()
        self.reload_galleries(log_message=False)

    def build_client_from_settings(self, settings_data):
        return build_image_client(settings_data)

    def apply_settings_to_ui(self):
        self.settings_data = merge_plugin_settings(self.settings_data)

        output_dir = self.settings_data.get("output_dir", DEFAULT_OUTPUT_DIR)
        self.output_dir_edit.setText(output_dir)

        model = self.settings_data.get("default_model", DEFAULT_MODEL)
        if self.model_combo.findText(model) < 0:
            self.model_combo.addItem(model)
        self.model_combo.setCurrentText(model)

        image_size = self.settings_data.get("default_image_size", DEFAULT_IMAGE_SIZE)
        if self.size_combo.findText(image_size) < 0:
            self.size_combo.addItem(image_size)
        self.size_combo.setCurrentText(image_size)

    def persist_output_dir_setting(self):
        self.settings_data = merge_plugin_settings(dict(self.settings_data, **{
            "output_dir": self.output_dir_edit.text().strip() or DEFAULT_OUTPUT_DIR
        }))
        save_plugin_settings(self.settings_data)

    def on_settings_clicked(self):
        old_output_dir = normalize_path_str(self.output_dir_edit.text().strip())

        current_settings = dict(self.settings_data)
        current_settings["output_dir"] = self.output_dir_edit.text().strip() or current_settings.get("output_dir",
                                                                                                     DEFAULT_OUTPUT_DIR)
        current_settings["default_model"] = self.model_combo.currentText().strip() or current_settings.get(
            "default_model", DEFAULT_MODEL)

        dlg = SettingsDialog(current_settings, self)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        self.settings_data = save_plugin_settings(dlg.get_settings())
        self.apply_settings_to_ui()
        self.refresh_client_settings()

        new_output_dir = normalize_path_str(self.output_dir_edit.text().strip())
        if old_output_dir != new_output_dir:
            self.clear_preview()
            self.reload_galleries(log_message=False)

        self.log("平台设置已保存: provider={} api_base={}".format(
            self.settings_data.get("provider", ""),
            self.settings_data.get("api_base", "")
        ))
        self.status_label.setText("设置已保存")

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(6)
        form.setVerticalSpacing(6)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)

        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.addItems([
            "nano-banana-2",
            "nano-banana-fast",
            "nano-banana",
            "nano-banana-pro",
            "nano-banana-pro-vt",
            "nano-banana-pro-cl",
            "nano-banana-pro-vip",
            "nano-banana-2-cl",
            "nano-banana-2-4k-cl",
            "nano-banana-pro-4k-vip",
        ])
        self.model_combo.setCurrentText(DEFAULT_MODEL)
        self.model_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed
        )

        self.size_combo = QtWidgets.QComboBox()
        self.size_combo.addItems(["1K", "2K", "4K"])
        self.size_combo.setCurrentText(DEFAULT_IMAGE_SIZE)
        self.size_combo.setFixedWidth(72)

        msa_widget = QtWidgets.QWidget()
        msa_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed
        )
        msa_layout = QtWidgets.QHBoxLayout(msa_widget)
        msa_layout.setContentsMargins(0, 0, 0, 0)
        msa_layout.setSpacing(4)
        msa_layout.addWidget(self.model_combo, 1)
        msa_layout.addWidget(self.size_combo, 0)
        form.addRow("Model", msa_widget)

        self.output_dir_edit = QtWidgets.QLineEdit()
        self.output_dir_edit.setText(os.path.expanduser("~/Pictures/sp_ai_outputs"))
        self.output_dir_edit.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed
        )

        self.open_dir_btn = QtWidgets.QPushButton("打开")
        self.open_dir_btn.setFixedWidth(72)

        output_widget = QtWidgets.QWidget()
        output_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed
        )
        output_layout = QtWidgets.QHBoxLayout(output_widget)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(4)
        output_layout.addWidget(self.output_dir_edit, 1)
        output_layout.addWidget(self.open_dir_btn, 0)
        form.addRow("Output", output_widget)

        self.prompt_edit = QtWidgets.QPlainTextEdit()
        self.prompt_edit.setPlaceholderText("例如：高细节科幻金属材质，红黑配色，边缘磨损，工业风，超清纹理表现")
        self.prompt_edit.setMinimumHeight(72)
        self.prompt_edit.setMaximumHeight(96)
        self.prompt_edit.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed
        )
        form.addRow("Prompt", self.prompt_edit)

        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems([MODE_SINGLE, MODE_MULTI, MODE_UV_GUIDE, MODE_PROMPT_ONLY])
        self.mode_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed
        )

        self.multi_set_label = QtWidgets.QLabel("视角")

        self.multi_set_combo = QtWidgets.QComboBox()
        self.multi_set_combo.addItems(["4视角", "6视角"])
        self.multi_set_combo.setCurrentText("6视角")
        self.multi_set_combo.setFixedWidth(76)

        self.ref_images_btn = QtWidgets.QPushButton("参考图(0)")
        self.ref_images_btn.setMinimumWidth(96)

        self.mode_row_widget = QtWidgets.QWidget()
        self.mode_row_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed
        )
        mode_row_layout = QtWidgets.QHBoxLayout(self.mode_row_widget)
        mode_row_layout.setContentsMargins(0, 0, 0, 0)
        mode_row_layout.setSpacing(4)
        mode_row_layout.addWidget(self.mode_combo, 1)
        mode_row_layout.addWidget(self.multi_set_label, 0)
        mode_row_layout.addWidget(self.multi_set_combo, 0)
        mode_row_layout.addWidget(self.ref_images_btn, 0)
        form.addRow("Mode", self.mode_row_widget)

        layout.addLayout(form)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)

        self.capture_btn = QtWidgets.QPushButton("截图")
        self.generate_btn = QtWidgets.QPushButton("生成")
        self.apply_btn = QtWidgets.QPushButton("映射")
        self.settings_btn = QtWidgets.QPushButton("设置")

        for b in [self.capture_btn, self.generate_btn, self.apply_btn, self.settings_btn]:
            b.setMinimumHeight(30)
            b.setMinimumWidth(0)
            b.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed
            )
            b.setStyleSheet("""
                QPushButton {
                    min-width: 0px;
                    padding: 4px 16px;
                }
            """)

        self.apply_btn.setEnabled(False)

        btn_layout.addWidget(self.capture_btn, 1)
        btn_layout.addWidget(self.generate_btn, 1)
        btn_layout.addWidget(self.apply_btn, 1)
        btn_layout.addWidget(self.settings_btn, 1)

        layout.addLayout(btn_layout)

        self.status_label = QtWidgets.QLabel("就绪")
        self.status_label.setStyleSheet("padding:2px 0;")
        layout.addWidget(self.status_label)

        self.preview_tabs = QtWidgets.QTabWidget()
        self.preview_tabs.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding
        )

        self.capture_list = self._create_thumb_list()
        self.capture_list.enable_file_drag = False

        self.capture_page = QtWidgets.QWidget()
        capture_layout = QtWidgets.QVBoxLayout(self.capture_page)
        capture_layout.setContentsMargins(2, 2, 2, 2)
        capture_layout.setSpacing(0)
        capture_layout.addWidget(self.capture_list)
        self.preview_tabs.addTab(self.capture_page, "截图")

        self.result_list = self._create_thumb_list()
        self.result_list.enable_file_drag = True
        self.result_list.drag_use_result_path = True

        self.result_page = QtWidgets.QWidget()
        result_layout = QtWidgets.QVBoxLayout(self.result_page)
        result_layout.setContentsMargins(2, 2, 2, 2)
        result_layout.setSpacing(0)
        result_layout.addWidget(self.result_list)
        self.preview_tabs.addTab(self.result_page, "结果")

        self.preview_page = QtWidgets.QWidget()
        preview_layout = QtWidgets.QVBoxLayout(self.preview_page)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        preview_layout.setSpacing(6)

        self.preview_info_label = QtWidgets.QLabel("")
        self.preview_info_label.setWordWrap(True)
        self.preview_info_label.setStyleSheet("color:#cfcfcf; padding:2px 0;")
        preview_layout.addWidget(self.preview_info_label, 0)

        self.preview_image = PreviewImageLabel()
        self.preview_image.setStyleSheet("background:#1f1f1f; border:1px solid #555;")
        preview_layout.addWidget(self.preview_image, 1)

        self.preview_tabs.addTab(self.preview_page, "预览")

        self.log_edit = QtWidgets.QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_page = QtWidgets.QWidget()
        log_layout = QtWidgets.QVBoxLayout(self.log_page)
        log_layout.setContentsMargins(2, 2, 2, 2)
        log_layout.setSpacing(0)
        log_layout.addWidget(self.log_edit)
        self.preview_tabs.addTab(self.log_page, "日志")

        layout.addWidget(self.preview_tabs, 1)

        self.capture_btn.clicked.connect(self.on_capture_clicked)
        self.generate_btn.clicked.connect(self.on_generate_clicked)
        self.apply_btn.clicked.connect(self.on_apply_clicked)
        self.settings_btn.clicked.connect(self.on_settings_clicked)
        self.open_dir_btn.clicked.connect(self.on_open_dir_clicked)
        self.output_dir_edit.editingFinished.connect(self.on_output_dir_changed)
        self.size_combo.currentTextChanged.connect(self.on_image_size_changed)

        self.capture_list.itemDoubleClicked.connect(self.on_capture_item_double_clicked)
        self.result_list.itemDoubleClicked.connect(self.on_result_item_double_clicked)

        self.capture_list.currentItemChanged.connect(self.on_capture_current_item_changed)
        self.result_list.currentItemChanged.connect(self.on_result_current_item_changed)

        self.capture_list.customContextMenuRequested.connect(self.on_capture_context_menu)
        self.result_list.customContextMenuRequested.connect(self.on_result_context_menu)

        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        self.preview_tabs.currentChanged.connect(self.on_preview_tab_changed)

        self.ref_images_btn.clicked.connect(self.on_reference_images_clicked)

        self.on_mode_changed(self.mode_combo.currentText())

    def _create_thumb_list(self):
        w = ThumbListWidget()
        w.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        w.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        w.setMovement(QtWidgets.QListView.Movement.Static)
        w.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        w.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        w.setIconSize(self.thumb_size)
        w.setGridSize(self.thumb_grid_size)
        w.setSpacing(6)
        w.setWrapping(True)
        w.setWordWrap(False)
        w.setItemDelegate(ThumbIconOnlyDelegate(self.thumb_size, w))

        w.setDragEnabled(True)
        w.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DragOnly)

        w.setStyleSheet("""
            QListWidget {
                background:#232323;
                border:1px solid #555;
                outline: none;
            }
            QListWidget::item {
                padding:0px;
                margin:0px;
                outline: none;
            }
            QListWidget::item:selected {
                background: transparent;
                border: none;
            }
        """)
        return w

    def get_valid_reference_image_paths(self):
        out = []
        seen = set()

        for p in self.reference_image_paths:
            path = str(p or "").strip()
            if not path or not os.path.exists(path):
                continue

            norm = normalize_path_str(path)
            if norm in seen:
                continue

            out.append(path)
            seen.add(norm)

        return out

    def default_prompt_candidates(self):
        return {
            DEFAULT_SINGLE_PROMPT,
            DEFAULT_SINGLE_REF_PROMPT,
            DEFAULT_MULTI_PROMPT,
            DEFAULT_MULTI_REF_PROMPT,
            DEFAULT_UV_GUIDE_PROMPT,
            DEFAULT_UV_GUIDE_REF_PROMPT,
            DEFAULT_PROMPT_ONLY_PROMPT,
            DEFAULT_PROMPT_ONLY_REF_PROMPT,
        }

    def refresh_prompt_by_mode_and_refs(self, force=False):
        mode = self.mode_combo.currentText()
        ref_count = len(self.get_valid_reference_image_paths())

        if mode == MODE_PROMPT_ONLY:
            status = "提示词生成模式（参考图{}张）".format(ref_count)
            target_prompt = DEFAULT_PROMPT_ONLY_REF_PROMPT if ref_count > 0 else DEFAULT_PROMPT_ONLY_PROMPT

        elif mode == MODE_UV_GUIDE:
            status = "UV导出模式（参考图{}张）".format(ref_count)
            target_prompt = DEFAULT_UV_GUIDE_REF_PROMPT if ref_count > 0 else DEFAULT_UV_GUIDE_PROMPT

        elif mode == MODE_MULTI:
            status = "多视角模式（参考图{}张）".format(ref_count)
            target_prompt = DEFAULT_MULTI_REF_PROMPT if ref_count > 0 else DEFAULT_MULTI_PROMPT

        else:
            status = "单视角模式（参考图{}张）".format(ref_count)
            target_prompt = DEFAULT_SINGLE_REF_PROMPT if ref_count > 0 else DEFAULT_SINGLE_PROMPT

        self.status_label.setText(status)

        current_text = self.prompt_edit.toPlainText()
        if force or current_text in self.default_prompt_candidates():
            self.prompt_edit.setPlainText(target_prompt)

    def refresh_reference_images_button_text(self):
        valid_paths = self.get_valid_reference_image_paths()
        count = len(valid_paths)

        self.ref_images_btn.setText("参考图({})".format(count))

        if count > 0:
            self.ref_images_btn.setToolTip("\n".join(valid_paths))
        else:
            self.ref_images_btn.setToolTip("点击管理参考图")

    def update_mode_ui(self):
        mode = self.mode_combo.currentText()
        is_multi = (mode == MODE_MULTI)

        self.multi_set_label.setVisible(is_multi)
        self.multi_set_combo.setVisible(is_multi)

        self.ref_images_btn.setVisible(True)
        self.refresh_reference_images_button_text()

    def on_reference_images_clicked(self):
        dlg = ReferenceImagesDialog(self.reference_image_paths, self)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        self.reference_image_paths = dlg.get_image_paths()
        self.refresh_reference_images_button_text()

        count = len(self.get_valid_reference_image_paths())
        self.log("参考图数量: {}".format(count))

        self.refresh_prompt_by_mode_and_refs(force=False)

    def build_submit_image_paths(self, capture_path=None):
        paths = []
        paths.extend(self.get_valid_reference_image_paths())

        if capture_path:
            paths.append(capture_path)

        return paths

    def build_uv_submit_image_paths(self, record):
        if not isinstance(record, dict):
            return []

        paths = []
        seen = set()

        def push(path):
            path = str(path or "").strip()
            if not path or not os.path.exists(path):
                return
            norm = normalize_path_str(path)
            if norm in seen:
                return
            seen.add(norm)
            paths.append(path)

        push(record.get("uv_layout_path") or record.get("capture_path"))

        push(record.get("multiview_atlas_path"))

        for p in self.get_valid_reference_image_paths():
            push(p)

        return paths

    def build_effective_prompt(self, base_prompt, mode, ref_count, has_capture):
        return (base_prompt or "").strip()

    def log(self, text):
        self.log_edit.appendPlainText(text)

    def set_status(self, text, write_log=False):
        self.status_label.setText(text)
        if write_log:
            self.log(text)
        QtWidgets.QApplication.processEvents()

    def set_status_and_log(self, text):
        self.status_label.setText(text)
        self.log(text)
        QtWidgets.QApplication.processEvents()

    def current_output_dir(self, create=True):
        path = self.output_dir_edit.text().strip()
        if not path:
            path = self.settings_data.get("output_dir", DEFAULT_OUTPUT_DIR) or DEFAULT_OUTPUT_DIR
            self.output_dir_edit.setText(path)
        return ensure_dir(path) if create else path

    def normalize_pixmap(self, pixmap):
        if pixmap is None or pixmap.isNull():
            return pixmap
        try:
            image = pixmap.toImage()
            image = image.convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
            return QtGui.QPixmap.fromImage(image)
        except Exception:
            return pixmap

    def make_placeholder_icon(self, text="AI"):
        canvas = QtGui.QPixmap(self.thumb_size)
        canvas.fill(QtGui.QColor("#2b2b2b"))
        painter = QtGui.QPainter(canvas)
        try:
            painter.setPen(QtGui.QColor("#555"))
            painter.drawRect(0, 0, self.thumb_size.width() - 1, self.thumb_size.height() - 1)
            font = painter.font()
            font.setBold(True)
            font.setPointSize(16)
            painter.setFont(font)
            painter.setPen(QtGui.QColor("#d0d0d0"))
            painter.drawText(canvas.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, text)
        finally:
            painter.end()
        return QtGui.QIcon(canvas)

    def make_thumb_icon(self, image_path):
        pixmap = QtGui.QPixmap(image_path)
        if pixmap.isNull():
            return self.make_placeholder_icon("X")

        pixmap = self.normalize_pixmap(pixmap)
        thumb = pixmap.scaled(
            self.thumb_size,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation
        )

        canvas = QtGui.QPixmap(self.thumb_size)
        canvas.fill(QtGui.QColor("#2b2b2b"))

        painter = QtGui.QPainter(canvas)
        try:
            x = int((self.thumb_size.width() - thumb.width()) / 2)
            y = int((self.thumb_size.height() - thumb.height()) / 2)
            painter.drawPixmap(x, y, thumb)
            painter.setPen(QtGui.QColor("#555"))
            painter.drawRect(0, 0, self.thumb_size.width() - 1, self.thumb_size.height() - 1)
        finally:
            painter.end()

        return QtGui.QIcon(canvas)

    def current_screen(self, widget):
        try:
            handle = widget.windowHandle()
            if handle is not None and handle.screen() is not None:
                return handle.screen()
        except Exception:
            pass
        return QtWidgets.QApplication.primaryScreen()

    def capture_main_window(self):
        main_window = substance_painter.ui.get_main_window()
        if main_window is None:
            raise RuntimeError("无法获取 Painter 主窗口")

        main_window.raise_()
        main_window.activateWindow()
        QtWidgets.QApplication.processEvents()
        QtCore.QThread.msleep(120)

        screen = self.current_screen(main_window)
        if screen is None:
            raise RuntimeError("无法获取屏幕对象")

        pixmap = screen.grabWindow(int(main_window.winId()))
        if pixmap.isNull():
            raise RuntimeError("窗口截图失败")

        return self.normalize_pixmap(pixmap)

    def _is_ignored_widget(self, w):
        if w is None:
            return True

        main_window = substance_painter.ui.get_main_window()
        if w == main_window:
            return True

        p = w
        while p is not None:
            if p is self:
                return True
            p = p.parentWidget()

        ignore_types = (
            QtWidgets.QDockWidget,
            QtWidgets.QMenuBar,
            QtWidgets.QStatusBar,
            QtWidgets.QToolBar,
            QtWidgets.QScrollBar,
            QtWidgets.QSplitter,
            QtWidgets.QTabBar,
        )

        if isinstance(w, ignore_types):
            return True
        if not w.isVisible():
            return True
        if w.width() < 200 or w.height() < 200:
            return True

        return False

    def find_viewport_widget(self):
        main_window = substance_painter.ui.get_main_window()
        if main_window is None:
            return None

        try:
            for w in main_window.findChildren(QtWidgets.QWidget):
                if self._is_ignored_widget(w):
                    continue
                if w.objectName() == "Viewer3D":
                    return w
        except Exception:
            pass

        try:
            candidates = []
            for w in main_window.findChildren(QtWidgets.QWidget):
                if self._is_ignored_widget(w):
                    continue
                area = w.width() * w.height()
                candidates.append((area, w))
            candidates.sort(key=lambda x: x[0], reverse=True)
            if candidates:
                return candidates[0][1]
        except Exception:
            pass

        return None

    def capture_viewport_widget(self):
        main_window = substance_painter.ui.get_main_window()
        if main_window is None:
            raise RuntimeError("无法获取 Painter 主窗口")

        target = self.find_viewport_widget()
        if target is None:
            return self.capture_main_window()

        try:
            main_window.raise_()
            main_window.activateWindow()
            QtWidgets.QApplication.processEvents()
            QtCore.QThread.msleep(120)

            screen = self.current_screen(main_window)
            if screen is not None:
                global_pos = target.mapToGlobal(QtCore.QPoint(0, 0))
                pixmap = screen.grabWindow(
                    0,
                    global_pos.x(),
                    global_pos.y(),
                    target.width(),
                    target.height()
                )
                if pixmap is not None and not pixmap.isNull():
                    return self.normalize_pixmap(pixmap)
        except Exception:
            pass

        try:
            pixmap = target.grab()
            if pixmap is not None and not pixmap.isNull():
                return self.normalize_pixmap(pixmap)
        except Exception:
            pass

        return self.capture_main_window()

    def capture_current_view(self):
        return self.capture_viewport_widget()

    def tap_f2(self, wait_ms=120):
        main_window = substance_painter.ui.get_main_window()
        if main_window is None:
            return False

        try:
            main_window.raise_()
            main_window.activateWindow()
            main_window.setFocus(QtCore.Qt.FocusReason.ActiveWindowFocusReason)
            QtWidgets.QApplication.processEvents()

            press_event = QtGui.QKeyEvent(
                QtCore.QEvent.Type.KeyPress,
                QtCore.Qt.Key.Key_F2,
                QtCore.Qt.KeyboardModifier.NoModifier
            )
            release_event = QtGui.QKeyEvent(
                QtCore.QEvent.Type.KeyRelease,
                QtCore.Qt.Key.Key_F2,
                QtCore.Qt.KeyboardModifier.NoModifier
            )

            QtWidgets.QApplication.sendEvent(main_window, press_event)
            QtWidgets.QApplication.processEvents()
            QtWidgets.QApplication.sendEvent(main_window, release_event)
            QtWidgets.QApplication.processEvents()

            QtCore.QThread.msleep(max(0, int(wait_ms)))
            self._flush_viewport_frames(frame_count=2, frame_sleep_ms=33)
            return True

        except Exception as e:
            self.log("模拟 F2 失败: {}".format(e))
            return False

    def has_camera_api(self):
        try:
            return (
                sp_display is not None and
                hasattr(sp_display, "Camera") and
                hasattr(sp_display.Camera, "get_default_camera")
            )
        except Exception:
            return False

    def get_camera_state(self):
        if not self.has_camera_api():
            raise RuntimeError("当前版本没有可用的相机 API")
        if not substance_painter.project.is_open():
            raise RuntimeError("当前没有打开工程，无法读取相机")

        camera = sp_display.Camera.get_default_camera()
        return {
            "position": list(camera.position),
            "rotation": list(camera.rotation),
            "field_of_view": float(camera.field_of_view),
            "focal_length": float(camera.focal_length),
            "focus_distance": float(camera.focus_distance),
            "aperture": float(camera.aperture),
            "orthographic_height": float(camera.orthographic_height),
            "projection_type": camera.projection_type.name,
        }

    def get_camera_state_safe(self):
        try:
            return self.get_camera_state()
        except Exception as e:
            self.log("读取相机失败: {}".format(e))
            return None

    def restore_camera_state(self, state):
        if not state:
            return
        if not self.has_camera_api():
            raise RuntimeError("当前版本没有可用的相机 API")
        if not substance_painter.project.is_open():
            raise RuntimeError("当前没有打开工程，无法恢复相机")

        camera = sp_display.Camera.get_default_camera()

        projection_name = state.get("projection_type")
        if projection_name and hasattr(sp_display.CameraProjectionType, projection_name):
            camera.projection_type = getattr(sp_display.CameraProjectionType, projection_name)

        if state.get("position") is not None:
            camera.position = list(state["position"])
        if state.get("rotation") is not None:
            camera.rotation = list(state["rotation"])

        for attr in ["field_of_view", "focal_length", "focus_distance", "aperture", "orthographic_height"]:
            if state.get(attr) is not None:
                try:
                    setattr(camera, attr, float(state[attr]))
                except Exception:
                    pass

    def restore_camera_state_safe(self, state):
        try:
            self.restore_camera_state(state)
        except Exception as e:
            self.log("恢复相机失败: {}".format(e))

    def get_scene_bbox_safe(self):
        try:
            if not substance_painter.project.is_open():
                raise RuntimeError("当前没有打开工程")
            return substance_painter.project.get_scene_bounding_box()
        except Exception as e:
            self.log("读取场景包围盒失败: {}".format(e))
            return None

    def _bbox_center_radius(self, bbox):
        center = list(bbox.center)
        radius = 1.0
        try:
            mn = list(bbox.minimum)
            mx = list(bbox.maximum)
            size = [float(mx[i] - mn[i]) for i in range(3)]
            radius = max(size) * 0.5
            if radius <= 1e-5:
                radius = 1.0
        except Exception:
            pass
        return center, radius

    def _bbox_size_safe(self, bbox):
        try:
            mn = list(bbox.minimum)
            mx = list(bbox.maximum)
            sx = max(float(mx[0] - mn[0]), 1e-6)
            sy = max(float(mx[1] - mn[1]), 1e-6)
            sz = max(float(mx[2] - mn[2]), 1e-6)
            return [sx, sy, sz]
        except Exception:
            return [1.0, 1.0, 1.0]

    def _make_camera_state_from_view(self, view_name, ortho=True, fit_scale=2.4):
        bbox = self.get_scene_bbox_safe()
        if bbox is None:
            raise RuntimeError("无法获取场景包围盒")

        center, radius = self._bbox_center_radius(bbox)
        dist = max(radius * fit_scale, 0.1)

        positions = {
            "front": [center[0], center[1], center[2] - dist],
            "back": [center[0], center[1], center[2] + dist],
            "left": [center[0] - dist, center[1], center[2]],
            "right": [center[0] + dist, center[1], center[2]],
            "top": [center[0], center[1] - dist, center[2]],
            "bottom": [center[0], center[1] + dist, center[2]],
        }

        if view_name not in positions:
            raise RuntimeError("未知视角: {}".format(view_name))

        rotation = list(MULTIVIEW_ROT_PRESETS.get(view_name, [0.0, 0.0, 0.0]))

        return {
            "position": positions[view_name],
            "rotation": rotation,
            "projection_type": "Orthographic" if ortho else "Perspective",
            "field_of_view": 35.0,
            "focal_length": 50.0,
            "focus_distance": dist,
            "aperture": 0.0,
            "orthographic_height": radius * 2.4,
        }

    def _clamp(self, value, mn, mx):
        return max(mn, min(mx, value))

    def _get_image_aspect_safe(self, image_path, default=1.0):
        try:
            if image_path and os.path.exists(image_path):
                img = QtGui.QImage(image_path)
                if not img.isNull() and img.height() > 0:
                    return float(img.width()) / float(img.height())
        except Exception:
            pass
        return float(default)

    def _normalize_angle_deg(self, value):
        v = float(value)
        while v > 180.0:
            v -= 360.0
        while v <= -180.0:
            v += 360.0
        return v

    def _float_close(self, a, b, tol):
        try:
            return abs(float(a) - float(b)) <= float(tol)
        except Exception:
            return False

    def _angle_close_deg(self, a, b, tol):
        try:
            d = self._normalize_angle_deg(float(a) - float(b))
            return abs(d) <= float(tol)
        except Exception:
            return False

    def _camera_state_close(self, cur, target, pos_tol=1e-3, rot_tol=0.5, ortho_tol=1e-3):
        if not isinstance(cur, dict) or not isinstance(target, dict):
            return False

        try:
            cp = list(cur.get("position", []))
            tp = list(target.get("position", []))
            cr = list(cur.get("rotation", []))
            tr = list(target.get("rotation", []))

            if len(cp) != 3 or len(tp) != 3 or len(cr) != 3 or len(tr) != 3:
                return False

            for i in range(3):
                if not self._float_close(cp[i], tp[i], pos_tol):
                    return False

            for i in range(3):
                if not self._angle_close_deg(cr[i], tr[i], rot_tol):
                    return False

            cur_proj = str(cur.get("projection_type", "") or "").lower()
            tar_proj = str(target.get("projection_type", "") or "").lower()
            if cur_proj != tar_proj:
                return False

            if "ortho" in tar_proj:
                ch = float(cur.get("orthographic_height") or 0.0)
                th = float(target.get("orthographic_height") or 0.0)
                if abs(ch - th) > ortho_tol:
                    return False

            return True
        except Exception:
            return False

    def _flush_viewport_frames(self, frame_count=6, frame_sleep_ms=33):
        viewport = self.find_viewport_widget()
        for _ in range(max(1, int(frame_count))):
            QtWidgets.QApplication.processEvents()
            try:
                if viewport is not None:
                    viewport.update()
                    viewport.repaint()
            except Exception:
                pass
            QtCore.QThread.msleep(max(1, int(frame_sleep_ms)))

    def apply_camera_state_and_wait(self, state, timeout_ms=1500):
        self.restore_camera_state_safe(state)

        deadline = time.time() + float(timeout_ms) / 1000.0
        matched = False
        last_state = None

        while time.time() < deadline:
            self._flush_viewport_frames(frame_count=1, frame_sleep_ms=33)
            last_state = self.get_camera_state_safe()
            if self._camera_state_close(last_state, state):
                matched = True
                break

        self._flush_viewport_frames(frame_count=5, frame_sleep_ms=33)

        return matched, last_state

    def _normalize_rotation_deg(self, rot):
        return [
            self._normalize_angle_deg(rot[0]),
            self._normalize_angle_deg(rot[1]),
            self._normalize_angle_deg(rot[2]),
        ]

    def _apply_projector_rotation_offset(self, rotation):
        r = [float(rotation[0]), float(rotation[1]), float(rotation[2])]
        r[0] += float(PROJECTOR_ROTATION_EULER_OFFSET[0])
        r[1] += float(PROJECTOR_ROTATION_EULER_OFFSET[1])
        r[2] += float(PROJECTOR_ROTATION_EULER_OFFSET[2])
        return self._normalize_rotation_deg(r)

    def _convert_camera_rotation_to_projector_rotation(self, camera_rotation, fallback_slot="front"):
        if camera_rotation is None:
            return self._apply_projector_rotation_offset(
                MULTIVIEW_ROT_PRESETS.get(fallback_slot, [0.0, 0.0, 0.0])
            )
        try:
            r = [
                float(camera_rotation[0]),
                float(camera_rotation[1]),
                float(camera_rotation[2]),
            ]
            return self._apply_projector_rotation_offset(r)
        except Exception:
            return self._apply_projector_rotation_offset(
                MULTIVIEW_ROT_PRESETS.get(fallback_slot, [0.0, 0.0, 0.0])
            )

    def _compute_view_height_from_camera(self, camera_state, radius, default_height):
        view_h = float(default_height)
        depth = max(radius * PROJECTOR_DEPTH_SCALE, 0.1)

        if not isinstance(camera_state, dict):
            return view_h, depth, "bbox_default"

        projection_type = str(camera_state.get("projection_type", "") or "").lower()

        try:
            if "ortho" in projection_type:
                ortho_h = float(camera_state.get("orthographic_height") or 0.0)
                if ortho_h > 1e-6:
                    view_h = ortho_h
                depth = max(radius * PROJECTOR_DEPTH_SCALE, view_h, 0.1)
                return view_h, depth, "camera_ortho"

            dist = float(camera_state.get("focus_distance") or 0.0)
            if dist <= 1e-6:
                dist = max(radius * 2.4, 0.1)

            fov_deg = float(camera_state.get("field_of_view") or 35.0)
            fov_deg = self._clamp(fov_deg, 1.0, 175.0)

            tmp_h = 2.0 * dist * math.tan(math.radians(fov_deg) * 0.5)
            if tmp_h > 1e-6 and math.isfinite(tmp_h):
                view_h = tmp_h

            depth = max(dist * 2.0, radius * 1.5, 0.1)
            return view_h, depth, "camera_perspective"
        except Exception:
            return view_h, depth, "bbox_default_fallback"

    def _world_to_projector_scale(self, world_size_xyz):
        bbox = self.get_scene_bbox_safe()
        if bbox is None:
            return [1.0, 1.0, 1.0]

        scene_size = self._bbox_size_safe(bbox)
        mul = float(PROJECTOR_GLOBAL_SCALE_MULTIPLIER)

        sx = max((float(world_size_xyz[0]) / float(scene_size[0])) * mul, 1e-4)
        sy = max((float(world_size_xyz[1]) / float(scene_size[1])) * mul, 1e-4)
        sz = max((float(world_size_xyz[2]) / float(scene_size[2])) * mul, 1e-4)

        return [sx, sy, sz]

    def build_projection_anchor_from_camera_state(
            self,
            camera_state,
            image_path=None,
            fallback_slot="front"
    ):
        bbox = self.get_scene_bbox_safe()
        if bbox is None:
            raise RuntimeError("无法获取场景包围盒")

        center, radius = self._bbox_center_radius(bbox)

        default_h_world = max(radius * PROJECTOR_VIEW_FIT_SCALE, 0.1)
        view_h_world, depth_world, size_source = self._compute_view_height_from_camera(
            camera_state=camera_state,
            radius=radius,
            default_height=default_h_world
        )

        rotation = self._convert_camera_rotation_to_projector_rotation(
            camera_rotation=camera_state.get("rotation") if isinstance(camera_state, dict) else None,
            fallback_slot=fallback_slot
        )

        aspect = self._get_image_aspect_safe(image_path, default=1.0)
        view_w_world = max(view_h_world * aspect, 0.1)

        proj_scale = self._world_to_projector_scale([
            view_w_world,
            view_h_world,
            depth_world
        ])

        return {
            "offset": [0.0, 0.0, 0.0],
            "rotation": rotation,
            "scale": proj_scale,
            "target": [float(center[0]), float(center[1]), float(center[2])],
            "aspect": float(view_w_world / max(view_h_world, 1e-6)),
            "radius": float(radius),
            "source": "single_scene_bbox_normalized",
            "size_source": size_source,
            "world_size": [float(view_w_world), float(view_h_world), float(depth_world)],
        }

    def build_projection_anchor_for_slot(self, slot_name, image_path=None, camera_state=None):
        aspect = self._get_image_aspect_safe(image_path, default=1.0)

        bbox = self.get_scene_bbox_safe()
        if bbox is None:
            raise RuntimeError("无法获取场景包围盒")

        center, radius = self._bbox_center_radius(bbox)

        base_rot = MULTIVIEW_ROT_PRESETS.get(slot_name, [0.0, 0.0, 0.0])
        rotation = self._apply_projector_rotation_offset(base_rot)

        default_h_world = max(radius * PROJECTOR_VIEW_FIT_SCALE, 0.1)
        view_h_world = default_h_world
        depth_world = max(radius * PROJECTOR_DEPTH_SCALE, 0.1)
        size_source = "slot_bbox_default"

        try:
            if isinstance(camera_state, dict):
                projection_type = str(camera_state.get("projection_type", "") or "").lower()

                if "ortho" in projection_type:
                    ortho_h = float(camera_state.get("orthographic_height") or 0.0)
                    if ortho_h > 1e-6:
                        view_h_world = ortho_h
                        size_source = "slot_camera_ortho"
                    depth_world = max(radius * PROJECTOR_DEPTH_SCALE, view_h_world, 0.1)
                else:
                    dist = float(camera_state.get("focus_distance") or 0.0)
                    if dist <= 1e-6:
                        dist = max(radius * 2.4, 0.1)

                    fov_deg = float(camera_state.get("field_of_view") or 35.0)
                    fov_deg = self._clamp(fov_deg, 1.0, 175.0)
                    tmp_h = 2.0 * dist * math.tan(math.radians(fov_deg) * 0.5)

                    if tmp_h > 1e-6 and math.isfinite(tmp_h):
                        view_h_world = tmp_h
                        size_source = "slot_camera_perspective"

                    depth_world = max(dist * 2.0, radius * 1.5, 0.1)
        except Exception:
            pass

        view_w_world = max(view_h_world * aspect, 0.1)
        proj_scale = self._world_to_projector_scale([
            view_w_world,
            view_h_world,
            depth_world
        ])

        return {
            "offset": [0.0, 0.0, 0.0],
            "rotation": rotation,
            "scale": proj_scale,
            "target": [float(center[0]), float(center[1]), float(center[2])],
            "aspect": float(aspect),
            "radius": float(radius),
            "source": "multiview_scene_bbox_normalized",
            "size_source": size_source,
            "slot_name": slot_name,
            "world_size": [float(view_w_world), float(view_h_world), float(depth_world)],
        }

    def save_capture_record(
            self,
            pixmap,
            output_dir,
            camera_state=None,
            extra=None
    ):
        ensure_dir(output_dir)
        stamp = unique_stamp()

        image_path = os.path.join(output_dir, "capture_{}.png".format(stamp))
        meta_path = os.path.join(output_dir, "capture_{}.json".format(stamp))

        ok = pixmap.save(image_path, "PNG")
        if not ok:
            raise RuntimeError("截图保存失败: {}".format(image_path))

        record = {
            "type": "capture",
            "time": now_str_readable(),
            "stamp": stamp,
            "capture_path": image_path,
            "camera_state": camera_state or None,
            "meta_path": meta_path,
        }
        if extra and isinstance(extra, dict):
            record.update(extra)

        write_json(meta_path, record)
        return record

    def record_tooltip(self, record):
        lines = []

        if record.get("time"):
            lines.append("时间: {}".format(record.get("time", "")))

        if record.get("is_normal_result"):
            lines.append("类型: 法线结果")
        elif record.get("is_uvguide_input"):
            lines.append("类型: UV自动导出输入")
        elif record.get("is_uv_result"):
            lines.append("类型: UV贴图结果")
        elif record.get("is_multiview_atlas"):
            lines.append("类型: 多视角拼图")
        elif record.get("mode") == MODE_PROMPT_ONLY:
            lines.append("类型: 提示词生成结果")
        elif record.get("type") == "result" and (record.get("mode") == MODE_MULTI or record.get("is_multiview_result")):
            lines.append("类型: 多视角结果")
        elif record.get("type") == "result":
            lines.append("类型: 单视角结果")
        else:
            lines.append("类型: 截图")

        if record.get("type") == "result":
            if record.get("model"):
                lines.append("Model: {}".format(record.get("model", "")))
            if record.get("aspect_ratio"):
                lines.append("Aspect: {}".format(record.get("aspect_ratio", "")))
            if record.get("image_size"):
                lines.append("Size: {}".format(record.get("image_size", "")))
            if record.get("prompt"):
                lines.append("Prompt: {}".format(record.get("prompt", "")))

        ref_paths = record.get("reference_image_paths", []) or []
        if ref_paths:
            lines.append("参考图数量: {}".format(len(ref_paths)))

        if record.get("capture_path"):
            lines.append("Capture: {}".format(record.get("capture_path", "")))
        if record.get("result_path"):
            lines.append("Result: {}".format(record.get("result_path", "")))
        if record.get("normal_source_mode"):
            lines.append("法线来源: {}".format(record.get("normal_source_mode", "")))
        lines.append("Camera: {}".format("yes" if record.get("camera_state") else "no"))

        return "\n".join(lines)

    def create_thumb_item(self, record, image_path, lazy_icon=False, lazy_text="AI"):
        item = QtWidgets.QListWidgetItem()
        item.setText("")
        item.setToolTip(self.record_tooltip(record))
        item.setIcon(self.make_placeholder_icon(lazy_text) if lazy_icon else self.make_thumb_icon(image_path))
        item.setData(QtCore.Qt.ItemDataRole.UserRole, record)
        item.setSizeHint(self.thumb_grid_size)
        return item

    def add_capture_item(self, record, select=False, prepend=True, lazy_icon=False):
        image_path = record.get("capture_path")
        if not image_path or not os.path.exists(image_path):
            return None

        item = self.create_thumb_item(
            record,
            image_path,
            lazy_icon=lazy_icon,
            lazy_text=(
                "UV" if record.get("is_uvguide_input")
                else ("MV" if record.get("is_multiview_atlas") else "CP")
            )
        )

        if prepend:
            self.capture_list.insertItem(0, item)
        else:
            self.capture_list.addItem(item)

        if select:
            self.capture_list.setCurrentItem(item)

        return item

    def add_result_item(self, record, select=False, prepend=True, lazy_icon=False):
        image_path = record.get("result_path")
        if not image_path or not os.path.exists(image_path):
            return None

        item = self.create_thumb_item(record, image_path, lazy_icon=lazy_icon, lazy_text="AI")

        if prepend:
            self.result_list.insertItem(0, item)
        else:
            self.result_list.addItem(item)

        if select:
            self.result_list.setCurrentItem(item)

        return item

    def clear_preview(self):
        self.current_preview_record = None
        self.preview_image.clear_source_pixmap()
        self.preview_info_label.setText("未选择图片")

    def _record_preview_path(self, record):
        if record.get("type") == "result":
            return record.get("result_path")
        return record.get("capture_path")

    def update_preview_info(self, record, image_path):
        parts = []

        if record.get("time"):
            parts.append("时间: {}".format(record.get("time", "")))

        if record.get("is_normal_result"):
            parts.append("类型: 法线结果")
        elif record.get("is_uvguide_input"):
            parts.append("类型: UV自动导出输入")
        elif record.get("is_uv_result"):
            parts.append("类型: UV贴图结果")
        elif record.get("is_multiview_atlas"):
            parts.append("类型: 多视角拼图")
        elif record.get("mode") == MODE_PROMPT_ONLY:
            parts.append("类型: 提示词生成结果")
        else:
            parts.append("类型: {}".format("结果" if record.get("type") == "result" else "截图"))

        if record.get("is_normal_result"):
            parts.append("说明: AI转换生成的法线贴图")
        elif record.get("is_multiview_atlas"):
            parts.append("说明: 多视角拼图")
        elif record.get("mode") == MODE_PROMPT_ONLY:
            parts.append("说明: 提示词生成，可附带参考图")
        elif record.get("type") == "result" and (record.get("mode") == MODE_MULTI or record.get("is_multiview_result")):
            parts.append("说明: 多视角结果")
        elif record.get("mode") == MODE_UV_GUIDE or record.get("is_uvguide_input") or record.get("is_uv_result"):
            parts.append("说明: UV导出模式")
        elif record.get("type") == "result" and record.get("mode") == MODE_SINGLE:
            parts.append("说明: 单视角结果")

        if record.get("normal_source_mode"):
            parts.append("法线来源: {}".format(record.get("normal_source_mode", "")))

        ref_paths = record.get("reference_image_paths", []) or []
        if ref_paths:
            parts.append("参考图数量: {}".format(len(ref_paths)))

        if record.get("type") == "result":
            if record.get("model"):
                parts.append("Model: {}".format(record.get("model", "")))
            if record.get("aspect_ratio"):
                parts.append("Aspect: {}".format(record.get("aspect_ratio", "")))
            if record.get("image_size"):
                parts.append("Size: {}".format(record.get("image_size", "")))
            if record.get("prompt"):
                parts.append("Prompt: {}".format(record.get("prompt", "")))

        if image_path:
            parts.append("文件: {}".format(image_path))

        self.preview_info_label.setText("\n".join(parts))

    def preview_record(self, record):
        image_path = self._record_preview_path(record)
        if not image_path or not os.path.exists(image_path):
            self.clear_preview()
            return

        pixmap = QtGui.QPixmap(image_path)
        if pixmap.isNull():
            self.preview_image.clear_source_pixmap()
            self.preview_info_label.setText("图片无法解码：{}".format(image_path))
            return

        self.current_preview_record = record
        self.preview_image.set_source_pixmap(self.normalize_pixmap(pixmap))
        self.update_preview_info(record, image_path)

    def open_record_external(self, record):
        image_path = self._record_preview_path(record)
        if not image_path or not os.path.exists(image_path):
            raise RuntimeError("图片不存在")
        url = QtCore.QUrl.fromLocalFile(image_path)
        ok = QtGui.QDesktopServices.openUrl(url)
        if not ok:
            raise RuntimeError("无法用系统默认程序打开图片")

    def focus_record_camera(self, record):
        camera_state = record.get("camera_state")
        if camera_state:
            self.restore_camera_state_safe(camera_state)
            self.status_label.setText("已定位对应视角")
        else:
            self.status_label.setText("该记录没有相机数据")

    def delete_record_files(self, record):
        removed = []
        removed_norm = set()

        def add_removed(path):
            norm = normalize_path_str(path)
            if norm not in removed_norm:
                removed_norm.add(norm)
                removed.append(path)

        def remove_file(path):
            path = str(path or "").strip()
            if not path:
                return False

            norm = normalize_path_str(path)
            if norm in removed_norm:
                return False

            if safe_remove(path):
                add_removed(path)
                return True
            return False

        def remove_dir(path):
            path = str(path or "").strip()
            if not path or not os.path.isdir(path):
                return False

            norm = normalize_path_str(path)
            if norm in removed_norm:
                return False

            try:
                shutil.rmtree(path, ignore_errors=True)
                add_removed(path)
                return True
            except Exception:
                return False

        if not isinstance(record, dict):
            return removed

        if record.get("type") == "capture":
            remove_file(record.get("capture_path"))
        elif record.get("type") == "result":
            remove_file(record.get("result_path"))

        remove_file(record.get("meta_path"))
        remove_file(record.get("raw_uv_result_path"))
        remove_file(record.get("composite_result_path"))
        remove_file(record.get("raw_tile_path"))
        remove_file(record.get("normal_source_result_path"))

        remove_file(record.get("uv_layout_path"))
        remove_file(record.get("multiview_atlas_path"))

        uvguide_manifest = record.get("uvguide_manifest") or {}
        if isinstance(uvguide_manifest, dict):
            remove_file(uvguide_manifest.get("composite_path"))
            remove_file(uvguide_manifest.get("multiview_atlas_path"))

        multiview_manifest = record.get("multiview_manifest") or {}
        if isinstance(multiview_manifest, dict):
            remove_file(multiview_manifest.get("atlas_path"))

        if record.get("type") == "result" and (
                record.get("mode") == MODE_MULTI or record.get("is_multiview_result")
        ):
            rp = str(record.get("result_path", "") or "").strip()
            if rp:
                split_dir = os.path.splitext(rp)[0] + "_tiles"
                remove_dir(split_dir)

        return removed

    def delete_record(self, list_widget, item):
        if item is None:
            return

        record = item.data(QtCore.Qt.ItemDataRole.UserRole) or {}
        removed = self.delete_record_files(record)

        if self.current_preview_record is not None:
            cur_meta = self.current_preview_record.get("meta_path")
            del_meta = record.get("meta_path")
            if cur_meta and del_meta and cur_meta == del_meta:
                self.clear_preview()

        row = list_widget.row(item)
        list_widget.takeItem(row)

        self.refresh_apply_button_from_selection()

        if removed:
            self.log("已删除: {}".format(" | ".join([p for p in removed if p])))
        else:
            self.log("记录已移除，但没有找到可删除的文件")

        self.status_label.setText("已删除记录")

    def _menu_exec(self, menu, pos):
        return menu.exec(pos)

    def show_context_menu(self, list_widget, pos):
        if hasattr(list_widget, "item_at_icon_pos"):
            item = list_widget.item_at_icon_pos(pos)
        else:
            item = list_widget.itemAt(pos)

        if item is None:
            return

        list_widget.setCurrentItem(item)
        record = item.data(QtCore.Qt.ItemDataRole.UserRole) or {}

        menu = QtWidgets.QMenu(list_widget)
        act_open_external = menu.addAction("打开")
        act_delete = menu.addAction("删除")

        act_focus = None
        act_convert_normal = None

        if record.get("camera_state") and not record.get("is_multiview_atlas") and not record.get("is_uvguide_input"):
            act_focus = menu.addAction("定位视角")

        supports_normal_convert = (
                list_widget is self.result_list and
                not record.get("is_normal_result") and
                (
                        record.get("is_uv_result") or
                        record.get("is_multiview_result") or
                        record.get("mode") == MODE_MULTI or
                        record.get("mode") == MODE_SINGLE
                )
        )

        if supports_normal_convert:
            act_convert_normal = menu.addAction("生成法线")

        action = self._menu_exec(menu, list_widget.mapToGlobal(pos))
        if action == act_open_external:
            try:
                self.open_record_external(record)
            except Exception as e:
                self.preview_tabs.setCurrentWidget(self.log_page)
                self.set_status("打开失败: {}".format(e))
        elif act_focus is not None and action == act_focus:
            self.focus_record_camera(record)
        elif act_convert_normal is not None and action == act_convert_normal:
            self.on_convert_result_to_normal(record)
        elif action == act_delete:
            self.delete_record(list_widget, item)

    def on_capture_context_menu(self, pos):
        self.show_context_menu(self.capture_list, pos)

    def on_result_context_menu(self, pos):
        self.show_context_menu(self.result_list, pos)

    def clear_list_selection(self, list_widget):
        list_widget.blockSignals(True)
        try:
            list_widget.clearSelection()
            list_widget.setCurrentItem(None)
        finally:
            list_widget.blockSignals(False)

    def switch_preview_tab(self, widget, keep_selection=False):
        self._suppress_tab_clear = keep_selection
        try:
            self.preview_tabs.setCurrentWidget(widget)
        finally:
            self._suppress_tab_clear = False

    def on_preview_tab_changed(self, index):
        if getattr(self, "_suppress_tab_clear", False):
            return

        current_widget = self.preview_tabs.widget(index)

        if current_widget is self.capture_page or current_widget is self.result_page:
            self.clear_list_selection(self.capture_list)
            self.clear_list_selection(self.result_list)
            self.clear_preview()
            self.refresh_apply_button_from_selection()

    def on_capture_current_item_changed(self, current, previous):
        if current is not None:
            self.preview_record(current.data(QtCore.Qt.ItemDataRole.UserRole) or {})
        self.refresh_apply_button_from_selection()

    def on_result_current_item_changed(self, current, previous):
        if current is not None:
            record = current.data(QtCore.Qt.ItemDataRole.UserRole) or {}
            self.preview_record(record)
        self.refresh_apply_button_from_selection()

    def on_capture_item_double_clicked(self, item):
        if item is None:
            return
        record = item.data(QtCore.Qt.ItemDataRole.UserRole) or {}
        if record.get("is_multiview_atlas") or record.get("is_uvguide_input"):
            return
        self.focus_record_camera(record)

    def on_result_item_double_clicked(self, item):
        if item is None:
            return
        record = item.data(QtCore.Qt.ItemDataRole.UserRole) or {}
        if record.get("is_uv_result"):
            return
        self.focus_record_camera(record)

    def find_capture_record_by_path(self, capture_path):
        if not capture_path:
            return None

        target = normalize_path_str(capture_path)

        for i in range(self.capture_list.count()):
            item = self.capture_list.item(i)
            if item is None:
                continue
            rec = item.data(QtCore.Qt.ItemDataRole.UserRole) or {}
            rec_path = normalize_path_str(rec.get("capture_path"))
            if rec_path == target:
                return rec

        output_dir = self.current_output_dir(create=False)
        if not output_dir or not os.path.exists(output_dir):
            return None

        capture_jsons = sorted(glob.glob(os.path.join(output_dir, "capture_*.json")), reverse=True)
        for json_path in capture_jsons:
            try:
                rec = read_json(json_path, default=None)
                if isinstance(rec, dict):
                    rec_path = normalize_path_str(rec.get("capture_path"))
                    if rec_path == target:
                        rec["meta_path"] = json_path
                        return rec
            except Exception:
                pass

        return None

    def get_multiview_manifest_from_record(self, record):
        if not isinstance(record, dict):
            return None

        manifest = record.get("multiview_manifest")
        if not isinstance(manifest, dict):
            return None

        tiles = manifest.get("tiles")
        if not isinstance(tiles, list) or not tiles:
            return None

        return manifest

    def build_apply_payload_from_result_record(self, record):
        if not isinstance(record, dict):
            return None

        if record.get("mode") == MODE_PROMPT_ONLY:
            return None

        result_path = record.get("result_path")
        if not result_path or not os.path.exists(result_path):
            return None

        if record.get("is_normal_result"):
            return {
                "mode": "normal_texture",
                "record": record
            }

        if record.get("is_uv_result"):
            return {
                "mode": "uv_texture",
                "record": record
            }

        is_multi_result = (
                record.get("mode") == MODE_MULTI or
                bool(record.get("is_multiview_result"))
        )

        if is_multi_result:
            capture_path = record.get("capture_path")
            if not capture_path or not os.path.exists(capture_path):
                return None

            capture_record = self.find_capture_record_by_path(capture_path)
            manifest = self.get_multiview_manifest_from_record(capture_record)
            if not manifest:
                return None

            return {
                "mode": MODE_MULTI,
                "result_path": result_path,
                "manifest": manifest
            }

        if record.get("camera_state"):
            return {
                "mode": MODE_SINGLE,
                "record": record
            }

        return None

    def refresh_apply_button_from_selection(self):
        if self.gen_running:
            self.pending_apply_payload = None
            self.apply_btn.setEnabled(False)
            return

        payload = None
        current_widget = self.preview_tabs.currentWidget()

        if current_widget is self.result_page:
            current_item = self.result_list.currentItem()
            if current_item is not None:
                record = current_item.data(QtCore.Qt.ItemDataRole.UserRole) or {}
                payload = self.build_apply_payload_from_result_record(record)

        self.pending_apply_payload = payload
        self.apply_btn.setEnabled(payload is not None)

    def reload_galleries(self, log_message=True):
        try:
            output_dir = self.current_output_dir(create=True)
            self.capture_list.clear()
            self.result_list.clear()

            capture_jsons = sorted(glob.glob(os.path.join(output_dir, "capture_*.json")), reverse=True)
            result_jsons = sorted(glob.glob(os.path.join(output_dir, "result_*.json")), reverse=True)

            for json_path in capture_jsons:
                try:
                    record = read_json(json_path, default=None)
                    if not isinstance(record, dict):
                        continue
                    record["meta_path"] = json_path
                    self.add_capture_item(record, select=False, prepend=False, lazy_icon=False)
                except Exception as e:
                    self.log("读取截图记录失败 {}: {}".format(json_path, e))

            for json_path in result_jsons:
                try:
                    record = read_json(json_path, default=None)
                    if not isinstance(record, dict):
                        continue
                    record["meta_path"] = json_path
                    self.add_result_item(record, select=False, prepend=False, lazy_icon=False)
                except Exception as e:
                    self.log("读取结果记录失败 {}: {}".format(json_path, e))

            self.refresh_apply_button_from_selection()

            if log_message:
                self.log("图库已刷新")
        except Exception as e:
            self.log("加载缩略图失败: {}".format(e))

    def on_mode_changed(self, text):
        self.update_mode_ui()
        self.refresh_prompt_by_mode_and_refs(force=True)

    def current_multiview_defs(self):
        return MULTIVIEW_SET_4 if self.multi_set_combo.currentText() == "4视角" else MULTIVIEW_SET_6

    def get_export_size_log2(self):
        text = self.size_combo.currentText().strip().upper()
        return {"1K": 10, "2K": 11, "4K": 12}.get(text, 10)

    def get_uv_export_preset_url(self):
        if sp_export is None:
            raise RuntimeError("export API 不可用")

        try:
            for p in sp_export.list_predefined_export_presets():
                if getattr(p, "name", "") == UV_EXPORT_PRESET_NAME:
                    return p.url
        except Exception:
            pass

        try:
            for p in sp_export.list_resource_export_presets():
                rid = getattr(p, "resource_id", None)
                if rid is not None:
                    url = str(rid.url())
                    if UV_EXPORT_PRESET_NAME.lower() in url.lower():
                        return url
        except Exception:
            pass

        raise RuntimeError("找不到导出预设: {}".format(UV_EXPORT_PRESET_NAME))

    def export_active_basecolor_map(self, output_dir):
        if sp_export is None or sp_textureset is None:
            raise RuntimeError("export/textureset API 不可用")
        if not substance_painter.project.is_open():
            raise RuntimeError("请先打开工程")

        ensure_dir(output_dir)

        stack = sp_textureset.get_active_stack()
        if stack is None:
            raise RuntimeError("当前没有 active stack")

        root_path = str(stack)
        preset_url = self.get_uv_export_preset_url()
        export_dir = ensure_dir(os.path.join(output_dir, "_uv_export_tmp_" + unique_stamp()))

        self.log("开始导出 BaseColor，导出目录: {}".format(export_dir))

        config = {
            "exportPath": export_dir,
            "defaultExportPreset": preset_url,
            "exportShaderParams": False,
            "exportList": [
                {
                    "rootPath": root_path
                }
            ],
            "exportParameters": [
                {
                    "parameters": {
                        "fileFormat": "png",
                        "bitDepth": "8",
                        "sizeLog2": self.get_export_size_log2(),
                        "paddingAlgorithm": "passthrough"
                    }
                }
            ]
        }

        result = sp_export.export_project_textures(config)
        status_name = getattr(result.status, "name", str(result.status))
        if "success" not in status_name.lower():
            raise RuntimeError("导出失败: {} | {}".format(status_name, getattr(result, "message", "")))

        textures = getattr(result, "textures", {}) or {}

        exported_files = []
        for _, paths in textures.items():
            for p in paths:
                if p and os.path.exists(p):
                    exported_files.append(p)

        if not exported_files:
            raise RuntimeError("导出完成，但没有找到输出文件")

        for p in exported_files:
            low = os.path.basename(p).lower()
            if "basecolor" in low or "base_color" in low or "base color" in low:
                self.log("BaseColor 导出完成: {}".format(p))
                return p, export_dir

        self.log("未找到显式 BaseColor 文件，使用首个导出文件: {}".format(exported_files[0]))
        return exported_files[0], export_dir

    def capture_multiview_and_build_atlas(self):
        if not substance_painter.project.is_open():
            raise RuntimeError("请先打开一个 Painter 工程")

        output_dir = self.current_output_dir(create=True)
        defs = self.current_multiview_defs()
        original_camera = self.get_camera_state_safe()

        temp_records = []
        try:
            for slot_name, slot_label in defs:
                self.set_status("自动采集视角: {}".format(slot_label))
                self.tap_f2()
                state = self._make_camera_state_from_view(slot_name, ortho=True, fit_scale=2.4)
                self.apply_camera_state_and_wait(state, timeout_ms=1500)
                self._flush_viewport_frames(frame_count=2, frame_sleep_ms=40)
                pixmap = self.capture_current_view()

                rec = self.save_capture_record(
                    pixmap=pixmap,
                    output_dir=output_dir,
                    camera_state=state,
                    extra={
                        "slot_name": slot_name,
                        "slot_label": slot_label,
                        "is_multiview_temp": True
                    }
                )
                temp_records.append(rec)
        finally:
            if original_camera:
                self.apply_camera_state_and_wait(original_camera, timeout_ms=1000)

        stamp = unique_stamp()
        tmp_atlas_path = os.path.join(output_dir, "multiview_input_{}.png".format(stamp))

        manifest = build_multiview_atlas(
            tile_records=temp_records,
            atlas_path=tmp_atlas_path,
            tile_size=DEFAULT_MULTI_TILE_SIZE
        )

        atlas_pixmap = load_pixmap_safe(tmp_atlas_path)
        atlas_record = self.save_capture_record(
            pixmap=atlas_pixmap,
            output_dir=output_dir,
            camera_state=None,
            extra={
                "is_multiview_atlas": True,
                "reference_image_paths": list(self.get_valid_reference_image_paths()),
            }
        )
        manifest["atlas_path"] = atlas_record["capture_path"]
        atlas_record["multiview_manifest"] = manifest
        write_json(atlas_record["meta_path"], atlas_record)

        for rec in temp_records:
            self.delete_record_files(rec)

        safe_remove(tmp_atlas_path)

        self.add_capture_item(atlas_record, select=True, prepend=True, lazy_icon=False)
        self.switch_preview_tab(self.capture_page, keep_selection=True)
        self.status_label.setText("多视角截图与拼图完成")
        self.log("多视角拼图记录已创建: {}".format(atlas_record["capture_path"]))
        return atlas_record

    def capture_uvguide_and_build_composite(self):
        if not substance_painter.project.is_open():
            raise RuntimeError("请先打开一个 Painter 工程")

        output_dir = self.current_output_dir(create=True)
        defs = MULTIVIEW_SET_4
        original_camera = self.get_camera_state_safe()

        temp_records = []
        uv_export_file = None
        uv_export_dir = None
        tmp_atlas_path = None

        try:
            for slot_name, slot_label in defs:
                self.set_status("采集 {}".format(slot_label))
                self.tap_f2()
                state = self._make_camera_state_from_view(slot_name, ortho=True, fit_scale=2.4)
                self.apply_camera_state_and_wait(state, timeout_ms=1500)
                self._flush_viewport_frames(frame_count=2, frame_sleep_ms=40)
                pixmap = self.capture_current_view()

                rec = self.save_capture_record(
                    pixmap=pixmap,
                    output_dir=output_dir,
                    camera_state=state,
                    extra={
                        "slot_name": slot_name,
                        "slot_label": slot_label,
                        "is_uvguide_temp": True
                    }
                )
                temp_records.append(rec)

            if original_camera:
                self.apply_camera_state_and_wait(original_camera, timeout_ms=1000)

            self.set_status("导出 BaseColor")
            uv_export_file, uv_export_dir = self.export_active_basecolor_map(output_dir)
            uv_pixmap = load_pixmap_safe(uv_export_file)

            stamp = unique_stamp()
            tmp_atlas_path = os.path.join(output_dir, "uvauto_views_tmp_{}.png".format(stamp))
            atlas_saved_path = os.path.join(output_dir, "uvguide_views_{}.png".format(stamp))

            atlas_manifest = build_multiview_atlas(
                tile_records=temp_records,
                atlas_path=tmp_atlas_path,
                tile_size=DEFAULT_UV_GUIDE_TILE_SIZE
            )

            shutil.copy2(tmp_atlas_path, atlas_saved_path)
            atlas_manifest["atlas_path"] = atlas_saved_path

            record = self.save_capture_record(
                pixmap=uv_pixmap,
                output_dir=output_dir,
                camera_state=None,
                extra={
                    "mode": MODE_UV_GUIDE,
                    "is_uvguide_input": True,
                    "uv_layout_path": "",
                    "multiview_atlas_path": atlas_saved_path,
                    "multiview_manifest": atlas_manifest,
                    "uv_input_mode": "uv_primary_with_multiview_reference",
                }
            )

            record["uv_layout_path"] = record.get("capture_path", "")
            write_json(record["meta_path"], record)

            self.add_capture_item(record, select=True, prepend=True, lazy_icon=False)
            self.switch_preview_tab(self.capture_page, keep_selection=True)
            self.status_label.setText("UV主图 + 多视角参考图完成")
            self.log("UV 主图已创建: {}".format(record["uv_layout_path"]))
            self.log("多视角参考图已创建: {}".format(record["multiview_atlas_path"]))
            return record

        finally:
            for rec in temp_records:
                self.delete_record_files(rec)

            if tmp_atlas_path:
                safe_remove(tmp_atlas_path)

            if uv_export_file:
                safe_remove(uv_export_file)
            if uv_export_dir and os.path.isdir(uv_export_dir):
                try:
                    shutil.rmtree(uv_export_dir, ignore_errors=True)
                except Exception:
                    pass

            if original_camera:
                try:
                    self.apply_camera_state_and_wait(original_camera, timeout_ms=1000)
                except Exception:
                    pass

    def on_capture_clicked(self):
        try:
            mode = self.mode_combo.currentText()

            if mode == MODE_PROMPT_ONLY:
                self.status_label.setText("提示词生成模式无需截图，直接点击生成")
                self.log("提示词生成模式无需截图")
                return

            if mode == MODE_MULTI:
                self.capture_multiview_and_build_atlas()
                return

            if mode == MODE_UV_GUIDE:
                self.capture_uvguide_and_build_composite()
                return

            output_dir = self.current_output_dir(create=True)

            self._flush_viewport_frames(frame_count=2, frame_sleep_ms=33)
            camera_state = self.get_camera_state_safe()

            raw_pixmap = self.capture_current_view()
            pixmap, single_view_manifest = normalize_square_contain_with_manifest(
                raw_pixmap,
                DEFAULT_MULTI_TILE_SIZE,
                bg=DEFAULT_ATLAS_BG
            )

            record = self.save_capture_record(
                pixmap=pixmap,
                output_dir=output_dir,
                camera_state=camera_state,
                extra={
                    "single_view_manifest": single_view_manifest,
                }
            )
            self.add_capture_item(record, select=True, prepend=True, lazy_icon=False)
            self.switch_preview_tab(self.capture_page, keep_selection=True)
            self.log("截图完成: {}".format(record["capture_path"]))
            self.status_label.setText("截图完成")

        except Exception as e:
            self.log(traceback.format_exc())
            self.preview_tabs.setCurrentWidget(self.log_page)
            self.set_status("截图失败: {}".format(e))

    def get_selected_capture_record(self):
        item = self.capture_list.currentItem()
        if item is None:
            return None
        record = item.data(QtCore.Qt.ItemDataRole.UserRole) or {}
        path = record.get("capture_path")
        if not path or not os.path.exists(path):
            return None
        return record

    def refresh_client_settings(self):
        self.settings_data = load_plugin_settings()
        s = self.settings_data

        self.client.api_base = (s.get("api_base", API_BASE) or API_BASE).rstrip("/")
        self.client.api_key = (s.get("api_key", "") or "").strip()
        self.client.submit_path = normalize_api_path(s.get("submit_path"), SUBMIT_PATH)
        self.client.result_path = normalize_api_path(s.get("result_path"), RESULT_PATH)
        self.client.poll_interval = float(s.get("poll_interval", DEFAULT_POLL_INTERVAL))
        self.client.poll_timeout = int(float(s.get("poll_timeout", DEFAULT_POLL_TIMEOUT)))
        self.client.auth_mode = (s.get("auth_mode", "bearer") or "bearer").strip().lower()

        if hasattr(self.client, "use_data_url_prefix"):
            self.client.use_data_url_prefix = bool(s.get("use_data_url_prefix", False))

        if hasattr(self.client, "upload_path"):
            self.client.upload_path = normalize_api_path(
                s.get("runninghub_upload_path"),
                RUNNINGHUB_UPLOAD_PATH
            )

        if hasattr(self.client, "upload_mode"):
            self.client.upload_mode = str(
                s.get("runninghub_upload_mode", RUNNINGHUB_UPLOAD_DATA_URI) or RUNNINGHUB_UPLOAD_DATA_URI
            ).strip().lower()

        invalid_values = {"", "API_KEY", "YOUR_API_KEY", "None", "null"}
        if (self.client.api_key or "").strip() in invalid_values:
            self.client.api_key = ""

    def cleanup_pending_job_temp_files(self, ctx=None):
        ctx = ctx or {}
        temp_export_path = str(ctx.get("temp_export_path", "") or "").strip()
        temp_export_dir = str(ctx.get("temp_export_dir", "") or "").strip()
        temp_split_dir = str(ctx.get("temp_split_dir", "") or "").strip()

        if temp_export_path:
            safe_remove(temp_export_path)

        if temp_export_dir and os.path.isdir(temp_export_dir):
            try:
                shutil.rmtree(temp_export_dir, ignore_errors=True)
            except Exception:
                pass

        if temp_split_dir and os.path.isdir(temp_split_dir):
            try:
                shutil.rmtree(temp_split_dir, ignore_errors=True)
            except Exception:
                pass

    def on_convert_result_to_normal(self, record):
        temp_export_path = None
        temp_export_dir = None
        temp_group = None
        split_dir = None

        try:
            if not substance_painter.project.is_open():
                raise RuntimeError("请先打开一个 Painter 工程")

            self.refresh_client_settings()

            if not self.client.api_key:
                raise RuntimeError("请先填写 API Key")

            if not isinstance(record, dict):
                raise RuntimeError("结果记录无效")

            result_path = record.get("result_path")
            if not result_path or not os.path.exists(result_path):
                raise RuntimeError("结果图片不存在")

            output_dir = self.current_output_dir(create=True)

            if record.get("is_uv_result"):
                self.log("检测到 UV 结果图，直接调用 AI 转法线")
                self.log("准备进入 AI 生成阶段...")

                ctx = {
                    "mode": "normal_from_uv",
                    "normal_source_mode": "uv",
                    "normal_source_result_path": result_path,
                    "reference_image_paths": list(self.get_valid_reference_image_paths()),
                    "record_capture_path": result_path,
                }
                self.start_background_generate(
                    capture_path=result_path,
                    camera_state=None,
                    ctx=ctx,
                    prompt_override=DEFAULT_NORMAL_PROMPT
                )
                return

            if record.get("mode") == MODE_MULTI or record.get("is_multiview_result"):
                self.log("检测到多视图结果图，先创建临时投射组，再导出颜色贴图，再调用 AI 转法线")

                payload = self.build_apply_payload_from_result_record(record)
                if not payload:
                    raise RuntimeError("多视图结果缺少可用映射信息")

                manifest = payload.get("manifest")
                if not isinstance(manifest, dict):
                    raise RuntimeError("多视图 manifest 不存在")

                self.set_status_and_log("正在切分多视图结果...")
                split_dir = os.path.splitext(result_path)[0] + "_tiles"
                split_tiles, split_manifest_path = split_multiview_result_by_manifest(
                    result_image_path=result_path,
                    manifest=manifest,
                    output_dir=split_dir
                )

                self.log("多视图结果已切图，共 {} 张".format(len(split_tiles)))

                self.set_status_and_log("正在创建临时投射组...")
                temp_group = self.create_multiview_projection_group(
                    split_tiles=split_tiles,
                    group_name="AI_NormalBake_Temp_{}".format(time.strftime("%H%M%S"))
                )

                self.log("临时投射组已创建")
                self.log("切图信息: {}".format(split_manifest_path))

                self.set_status_and_log("正在导出颜色贴图...")
                temp_export_path, temp_export_dir = self.export_active_basecolor_map(output_dir)

                self.set_status_and_log("正在清理临时投射组...")
                self.remove_group_safe(temp_group)
                temp_group = None

                self.log("颜色贴图导出完成: {}".format(temp_export_path))
                self.log("准备进入 AI 生成阶段...")

                ctx = {
                    "mode": "normal_from_multiview",
                    "normal_source_mode": "multiview",
                    "normal_source_result_path": result_path,
                    "temp_export_path": temp_export_path,
                    "temp_export_dir": temp_export_dir,
                    "temp_split_dir": split_dir,
                    "reference_image_paths": list(self.get_valid_reference_image_paths()),
                    "record_capture_path": temp_export_path,
                }
                self.start_background_generate(
                    capture_path=temp_export_path,
                    camera_state=None,
                    ctx=ctx,
                    prompt_override=DEFAULT_NORMAL_PROMPT
                )
                return

            if record.get("mode") == MODE_SINGLE:
                self.log("检测到单视角结果图，直接调用 AI 转细节法线")
                self.log("准备进入 AI 生成阶段...")

                ctx = {
                    "mode": "normal_from_single",
                    "normal_source_mode": "single",
                    "normal_source_result_path": result_path,
                    "reference_image_paths": list(self.get_valid_reference_image_paths()),
                    "record_capture_path": result_path,
                }
                self.start_background_generate(
                    capture_path=result_path,
                    camera_state=None,
                    ctx=ctx,
                    prompt_override=DEFAULT_NORMAL_PROMPT
                )
                return

            raise RuntimeError("当前结果类型不支持转换为法线")

        except Exception as e:
            if temp_group is not None:
                try:
                    self.remove_group_safe(temp_group)
                except Exception:
                    pass

            if temp_export_path:
                safe_remove(temp_export_path)

            if temp_export_dir and os.path.isdir(temp_export_dir):
                try:
                    shutil.rmtree(temp_export_dir, ignore_errors=True)
                except Exception:
                    pass

            if split_dir and os.path.isdir(split_dir):
                try:
                    shutil.rmtree(split_dir, ignore_errors=True)
                except Exception:
                    pass

            self.log(traceback.format_exc())
            self.preview_tabs.setCurrentWidget(self.log_page)
            self.set_status("转换法线失败: {}".format(e))

    def clear_generate_queue(self):
        try:
            while True:
                self.gen_queue.get_nowait()
        except py_queue.Empty:
            pass

    def set_ui_busy(self, busy):
        self.capture_btn.setEnabled(not busy)
        self.generate_btn.setEnabled(not busy)
        self.settings_btn.setEnabled(not busy)
        self.open_dir_btn.setEnabled(not busy)
        self.mode_combo.setEnabled(not busy)
        self.multi_set_combo.setEnabled(not busy)
        self.ref_images_btn.setEnabled(not busy)

        if busy:
            self.apply_btn.setEnabled(False)
        else:
            self.refresh_apply_button_from_selection()

    def start_background_generate(self, capture_path=None, input_image_paths=None, camera_state=None, ctx=None,
                                  prompt_override=None, aspect_ratio_override=None):
        if self.gen_running:
            raise RuntimeError("已有生成任务正在运行")

        ctx = ctx or {}

        self.gen_running = True
        self.gen_cancel_requested = False
        self.pending_job_context = ctx
        self.clear_generate_queue()
        self.set_ui_busy(True)
        self.preview_tabs.setCurrentWidget(self.log_page)
        self._last_progress_log_text = ""

        user_prompt = self.prompt_edit.toPlainText().strip()
        prompt = prompt_override if prompt_override is not None else user_prompt

        model = self.model_combo.currentText().strip()
        aspect_ratio = str(aspect_ratio_override or "auto").strip() or "auto"
        image_size = self.size_combo.currentText().strip()
        output_dir = self.current_output_dir(create=True)

        submit_image_paths = list(input_image_paths or [])
        if not submit_image_paths and capture_path:
            submit_image_paths = [capture_path]

        record_capture_path = str(ctx.get("record_capture_path", capture_path or "") or "").strip()

        def progress_cb(text):
            self.gen_queue.put({
                "type": "progress",
                "text": text
            })

        def cancel_cb():
            return self.gen_cancel_requested

        def thread_main():
            try:
                progress_cb("正在提交 nano-banana...")

                if submit_image_paths:
                    if len(submit_image_paths) == 1:
                        image_bytes = self.client.generate_from_image(
                            image_path=submit_image_paths[0],
                            prompt=prompt,
                            model=model,
                            aspect_ratio=aspect_ratio,
                            image_size=image_size,
                            shut_progress=True,
                            progress_cb=progress_cb,
                            cancel_cb=cancel_cb
                        )
                    else:
                        image_bytes = self.client.generate_from_images(
                            image_paths=submit_image_paths,
                            prompt=prompt,
                            model=model,
                            aspect_ratio=aspect_ratio,
                            image_size=image_size,
                            shut_progress=True,
                            progress_cb=progress_cb,
                            cancel_cb=cancel_cb
                        )
                else:
                    image_bytes = self.client.generate_from_prompt(
                        prompt=prompt,
                        model=model,
                        aspect_ratio=aspect_ratio,
                        image_size=image_size,
                        shut_progress=True,
                        progress_cb=progress_cb,
                        cancel_cb=cancel_cb
                    )

                ensure_dir(output_dir)

                stamp = unique_stamp()
                save_path = os.path.join(output_dir, "result_{}.png".format(stamp))
                meta_path = os.path.join(output_dir, "result_{}.json".format(stamp))

                safe_bytes = sanitize_png_bytes(image_bytes)
                write_binary(save_path, safe_bytes)

                img = QtGui.QImage(save_path)
                if img.isNull():
                    safe_remove(save_path)
                    raise RuntimeError("结果图生成失败：返回内容不是有效图片")

                record = {
                    "type": "result",
                    "time": now_str_readable(),
                    "stamp": stamp,
                    "capture_path": record_capture_path,
                    "result_path": save_path,
                    "prompt": prompt,
                    "model": model,
                    "aspect_ratio": aspect_ratio,
                    "image_size": image_size,
                    "camera_state": camera_state or None,
                    "meta_path": meta_path,
                    "reference_image_paths": list(ctx.get("reference_image_paths", [])),
                    "submitted_image_paths": list(submit_image_paths),
                }

                if ctx.get("single_view_manifest"):
                    record["single_view_manifest"] = ctx.get("single_view_manifest")

                mode = ctx.get("mode")

                if mode == MODE_PROMPT_ONLY:
                    record["mode"] = MODE_PROMPT_ONLY

                elif mode == MODE_UV_GUIDE:
                    record["mode"] = MODE_UV_GUIDE
                    record["is_uv_result"] = True
                    record["uvguide_manifest"] = ctx.get("uvguide_manifest")

                elif mode == MODE_MULTI:
                    record["mode"] = MODE_MULTI
                    record["is_multiview_result"] = True

                elif mode == "normal_from_uv":
                    record["mode"] = "normal"
                    record["is_normal_result"] = True
                    record["normal_source_mode"] = "uv"
                    record["normal_source_result_path"] = ctx.get("normal_source_result_path", "")

                elif mode == "normal_from_multiview":
                    record["mode"] = "normal"
                    record["is_normal_result"] = True
                    record["normal_source_mode"] = "multiview"
                    record["normal_source_result_path"] = ctx.get("normal_source_result_path", "")

                elif mode == "normal_from_single":
                    record["mode"] = "normal"
                    record["is_normal_result"] = True
                    record["normal_source_mode"] = "single"
                    record["normal_source_result_path"] = ctx.get("normal_source_result_path", "")

                else:
                    record["mode"] = MODE_SINGLE

                write_json(meta_path, record)

                self.gen_queue.put({
                    "type": "finished",
                    "record": record
                })

            except Exception as e:
                self.gen_queue.put({
                    "type": "error",
                    "text": str(e),
                    "trace": traceback.format_exc()
                })

        self.gen_thread = threading.Thread(target=thread_main, daemon=True)
        self.gen_thread.start()
        self.gen_poll_timer.start()

    def poll_generate_queue(self):
        processed = False

        while True:
            try:
                msg = self.gen_queue.get_nowait()
            except py_queue.Empty:
                break

            processed = True
            mtype = msg.get("type")

            if mtype == "progress":
                text = msg.get("text", "处理中...")
                self.set_status(text)

                if text != self._last_progress_log_text:
                    self.log(text)
                    self._last_progress_log_text = text

            elif mtype == "error":
                ctx = self.pending_job_context or {}
                self.cleanup_pending_job_temp_files(ctx)
                self.pending_job_context = None
                self._last_progress_log_text = ""

                self.gen_running = False
                self.gen_thread = None
                self.gen_poll_timer.stop()
                self.set_ui_busy(False)
                self.log(msg.get("trace", ""))
                self.preview_tabs.setCurrentWidget(self.log_page)
                self.set_status("生成失败: {}".format(msg.get("text", "unknown")))
                return

            elif mtype == "finished":
                self._last_progress_log_text = ""

                self.gen_running = False
                self.gen_thread = None
                self.gen_poll_timer.stop()
                self.set_ui_busy(False)
                self.handle_generate_finished(msg.get("record") or {})
                return

        if not processed and not self.gen_running:
            self.gen_poll_timer.stop()

    def get_capture_record_expected_mode(self, record):
        if not isinstance(record, dict):
            return None

        if record.get("is_uvguide_input"):
            return MODE_UV_GUIDE

        if record.get("is_multiview_atlas"):
            return MODE_MULTI

        return MODE_SINGLE

    def validate_record_mode_match(self, record):
        if record.get("is_single_ref_input") or record.get("single_ref_manifest"):
            raise RuntimeError("检测到旧版数据记录，请重新截图后再生成")

        expected_mode = self.get_capture_record_expected_mode(record)
        current_mode = self.mode_combo.currentText()

        if expected_mode and current_mode != expected_mode:
            raise RuntimeError(
                "模式不匹配：当前是【{}】，请切到【{}】".format(
                    current_mode,
                    expected_mode
                )
            )

    def on_generate_clicked(self):
        try:
            if not substance_painter.project.is_open():
                raise RuntimeError("请先打开一个 Painter 工程")

            self.refresh_client_settings()

            if not self.client.api_key:
                self.preview_tabs.setCurrentWidget(self.log_page)
                self.set_status("请先填写 API Key", write_log=True)
                return

            prompt = self.prompt_edit.toPlainText().strip()
            if not prompt:
                raise RuntimeError("请填写 Prompt")

            mode = self.mode_combo.currentText()
            ref_paths = self.get_valid_reference_image_paths()

            if mode == MODE_PROMPT_ONLY:
                effective_prompt = self.build_effective_prompt(
                    base_prompt=prompt,
                    mode=mode,
                    ref_count=len(ref_paths),
                    has_capture=False
                )

                self.log("提示词生成模式")
                if ref_paths:
                    self.log("附加参考图 {} 张".format(len(ref_paths)))

                self.start_background_generate(
                    capture_path=None,
                    input_image_paths=ref_paths if ref_paths else None,
                    camera_state=None,
                    ctx={
                        "mode": MODE_PROMPT_ONLY,
                        "reference_image_paths": list(ref_paths),
                        "record_capture_path": "",
                    },
                    prompt_override=effective_prompt
                )
                return

            selected_record = self.get_selected_capture_record()
            if selected_record is None:
                raise RuntimeError("请先在截图页选中一张截图")

            self.validate_record_mode_match(selected_record)

            capture_path = selected_record.get("capture_path")
            if not capture_path or not os.path.exists(capture_path):
                raise RuntimeError("选中的截图文件不存在")

            submit_paths = self.build_submit_image_paths(capture_path)
            effective_prompt = self.build_effective_prompt(
                base_prompt=prompt,
                mode=mode,
                ref_count=len(ref_paths),
                has_capture=True
            )

            is_uvguide_capture = bool(selected_record.get("is_uvguide_input"))
            if is_uvguide_capture:
                uv_layout_path = str(selected_record.get("uv_layout_path") or capture_path or "").strip()
                multiview_atlas_path = str(selected_record.get("multiview_atlas_path") or "").strip()

                if not uv_layout_path or not os.path.exists(uv_layout_path):
                    raise RuntimeError("UV 主图不存在")

                if not multiview_atlas_path or not os.path.exists(multiview_atlas_path):
                    raise RuntimeError("当前 UV 记录缺少多视角参考图，请重新截图")

                submit_paths = self.build_uv_submit_image_paths(selected_record)
                if not submit_paths:
                    raise RuntimeError("UV 模式没有可提交的输入图")

                uv_aspect_ratio = "1:1"

                self.log("UV 模式生成（UV主图 + 多视角参考图）")
                self.log("UV 主图尺寸: {}x{}".format(*get_image_size_safe(uv_layout_path)))
                self.log("多视角参考图尺寸: {}x{}".format(*get_image_size_safe(multiview_atlas_path)))
                self.log("UV 输出比例: {}".format(uv_aspect_ratio))
                self.log("提交图像数: {}".format(len(submit_paths)))
                for idx, p in enumerate(submit_paths):
                    w, h = get_image_size_safe(p)
                    self.log("  [{}] {} | {}x{}".format(idx, p, w, h))

                if ref_paths:
                    self.log("附加用户参考图 {} 张".format(len(ref_paths)))

                ctx = {
                    "mode": MODE_UV_GUIDE,
                    "reference_image_paths": list(ref_paths),
                    "record_capture_path": uv_layout_path,
                    "uv_layout_path": uv_layout_path,
                    "multiview_atlas_path": multiview_atlas_path,
                }

                self.start_background_generate(
                    capture_path=uv_layout_path,
                    input_image_paths=submit_paths,
                    camera_state=None,
                    ctx=ctx,
                    prompt_override=effective_prompt,
                    aspect_ratio_override=uv_aspect_ratio
                )
                return

            is_multiview_capture = bool(selected_record.get("is_multiview_atlas"))
            if is_multiview_capture:
                manifest = self.get_multiview_manifest_from_record(selected_record)
                if not manifest:
                    raise RuntimeError("多视角 manifest 不存在")

                self.log("多视角模式生成")
                self.log("多视角输入尺寸: {}x{}".format(*get_image_size_safe(capture_path)))
                self.log("多视角比例策略: auto")
                if ref_paths:
                    self.log("附加参考图 {} 张".format(len(ref_paths)))

                ctx = {
                    "mode": MODE_MULTI,
                    "reference_image_paths": list(ref_paths),
                    "record_capture_path": capture_path,
                }

                self.start_background_generate(
                    capture_path=capture_path,
                    input_image_paths=submit_paths,
                    camera_state=None,
                    ctx=ctx,
                    prompt_override=effective_prompt
                )
                return

            camera_state = selected_record.get("camera_state")
            if not camera_state:
                raise RuntimeError("单视角截图缺少 camera_state，无法按单视角生成")

            self.log("单视角模式生成")
            if ref_paths:
                self.log("附加参考图 {} 张".format(len(ref_paths)))

            ctx = {
                "mode": MODE_SINGLE,
                "single_view_manifest": selected_record.get("single_view_manifest"),
                "reference_image_paths": list(ref_paths),
                "record_capture_path": capture_path,
            }

            self.start_background_generate(
                capture_path=capture_path,
                input_image_paths=submit_paths,
                camera_state=camera_state,
                ctx=ctx,
                prompt_override=effective_prompt
            )

        except Exception as e:
            self.set_ui_busy(False)
            self.preview_tabs.setCurrentWidget(self.log_page)
            self.set_status("生成失败: {}".format(e), write_log=True)

    def handle_generate_finished(self, record):
        ctx = self.pending_job_context or {}
        self.pending_job_context = None

        try:
            result_path = record.get("result_path")
            self.last_result_path = result_path

            if not result_path or not os.path.exists(result_path):
                self.preview_tabs.setCurrentWidget(self.log_page)
                self.set_status("生成完成，但结果图片无效")
                return

            img = QtGui.QImage(result_path)
            if img.isNull():
                self.preview_tabs.setCurrentWidget(self.log_page)
                self.set_status("生成完成，但结果图片无法解码")
                return

            if (
                    record.get("mode") == MODE_SINGLE and
                    record.get("single_view_manifest")
            ):
                try:
                    full_result_path = result_path
                    cropped_result_path = os.path.splitext(full_result_path)[0] + "_view.png"

                    crop_info = split_single_result_by_manifest(
                        result_image_path=full_result_path,
                        manifest=record.get("single_view_manifest"),
                        output_path=cropped_result_path
                    )

                    record["composite_result_path"] = full_result_path
                    record["result_path"] = crop_info["result_path"]
                    self.last_result_path = record["result_path"]
                    write_json(record["meta_path"], record)
                    result_path = record["result_path"]
                except Exception as e:
                    self.log("单视角结果裁切失败，保留整图结果: {}".format(e))

            item = self.add_result_item(record, select=False, prepend=True, lazy_icon=False)

            self.switch_preview_tab(self.result_page, keep_selection=True)

            if item is not None:
                self.result_list.setCurrentItem(item)
                self.preview_record(record)

            self.log("生成完成，保存于: {}".format(result_path))
            self.status_label.setText("生成完成")
            self.refresh_apply_button_from_selection()

        finally:
            self.cleanup_pending_job_temp_files(ctx)

    def get_texture_usage_for_import(self):
        if sp_resource is None or not hasattr(sp_resource, "Usage"):
            raise RuntimeError("resource.Usage 不可用")

        usage_members = getattr(sp_resource.Usage, "__members__", {})
        for name in ["Texture", "Textures", "Bitmap", "Image"]:
            if name in usage_members:
                return getattr(sp_resource.Usage, name)

        for name in usage_members.keys():
            low = name.lower()
            if "texture" in low or "bitmap" in low or "image" in low:
                return getattr(sp_resource.Usage, name)

        raise RuntimeError("未能识别导入 Usage")

    def import_image_as_project_resource(self, image_path, name=None, group="AIViewToPaint"):
        usage = self.get_texture_usage_for_import()
        return sp_resource.import_project_resource(
            file_path=image_path,
            resource_usage=usage,
            name=name,
            group=group
        )

    def get_active_stack_safe(self):
        if sp_textureset is None:
            raise RuntimeError("textureset API 不可用")
        stack = sp_textureset.get_active_stack()
        if stack is None:
            raise RuntimeError("当前没有 active stack")
        return stack

    def create_group_at_stack_top(self, stack, group_name):
        pos = sp_layerstack.InsertPosition.from_textureset_stack(stack)
        group = sp_layerstack.insert_group(pos)
        group.set_name(group_name)
        try:
            group.set_collapsed(False)
        except Exception:
            pass
        return group

    def delete_layerstack_node_safe(self, node):
        if node is None or sp_layerstack is None:
            return False

        delete_names = [
            "delete_node",
            "remove_node",
            "erase_node",
            "delete",
            "remove",
        ]

        for name in delete_names:
            fn = getattr(sp_layerstack, name, None)
            if callable(fn):
                try:
                    fn(node)
                    return True
                except Exception:
                    pass

        try:
            parent = getattr(node, "parent", None)
            if callable(parent):
                parent_node = parent()
                if parent_node is not None:
                    for name in delete_names:
                        fn = getattr(parent_node, name, None)
                        if callable(fn):
                            try:
                                fn(node)
                                return True
                            except Exception:
                                pass
        except Exception:
            pass

        return False

    def remove_group_safe(self, group):
        if group is None:
            return

        ok = self.delete_layerstack_node_safe(group)
        if ok:
            self.log("已清理临时组")
        else:
            self.log("警告：临时组删除失败，请手动检查图层栈")

    def set_fill_bitmap_source_channel(self, fill_node, channel_type, resource_id):
        active = set(fill_node.active_channels)
        active.add(channel_type)
        fill_node.active_channels = active
        return fill_node.set_source(channel_type, resource_id)

    def set_fill_bitmap_source_basecolor(self, fill_node, resource_id):
        return self.set_fill_bitmap_source_channel(
            fill_node,
            sp_textureset.ChannelType.BaseColor,
            resource_id
        )

    def set_fill_bitmap_source_normal(self, fill_node, resource_id):
        return self.set_fill_bitmap_source_channel(
            fill_node,
            sp_textureset.ChannelType.Normal,
            resource_id
        )

    def make_planar_params_for_slot(self, slot_name, anchor=None):
        if anchor is not None:
            offset = list(anchor.get("offset", [0.0, 0.0, 0.0]))
            rotation = list(anchor.get("rotation", MULTIVIEW_ROT_PRESETS.get(slot_name, [0.0, 0.0, 0.0])))
            scale = list(anchor.get("scale", [1.0, 1.0, 1.0]))
        else:
            rotation = self._apply_projector_rotation_offset(
                MULTIVIEW_ROT_PRESETS.get(slot_name, [0.0, 0.0, 0.0])
            )
            offset = [0.0, 0.0, 0.0]
            base = float(PROJECTOR_GLOBAL_SCALE_MULTIPLIER)
            scale = [base, base, base]

        if slot_name in ("front", "back"):
            culling_hardness = 0.75
        else:
            culling_hardness = 0.0

        projection_3d = sp_layerstack.Projection3DParams(
            offset=offset,
            rotation=rotation,
            scale=scale
        )

        return sp_layerstack.PlanarProjectionParams(
            filtering_mode=sp_layerstack.FilteringMode.BilinearHQ,
            uv_wrapping_mode=sp_layerstack.UVWrapMode.RepeatNone,
            shape_crop_mode=sp_layerstack.ShapeCropMode.CroppedToShape,
            depth_culling=sp_layerstack.ProjectionCullingParams(
                enabled=True,
                hardness=culling_hardness
            ),
            backface_culling=sp_layerstack.ProjectionCullingParams(
                enabled=True,
                hardness=culling_hardness
            ),
            backface_culling_angle=90.0,
            uv_transformation=sp_layerstack.UVTransformationParams(
                scale_mode=sp_layerstack.ScaleMode.Factors,
                scale=[1.0, 1.0],
                rotation=0.0,
                offset=[0.0, 0.0],
            ),
            projection_3d=projection_3d
        )

    def create_multiview_fill_layer(self, parent_group, slot_name, slot_label, resource_id, camera_state=None, image_path=None):
        pos = sp_layerstack.InsertPosition.inside_node(
            parent_group,
            sp_layerstack.NodeStack.Substack
        )
        fill = sp_layerstack.insert_fill(pos)
        fill.set_name("AI_{}".format(slot_label))
        self.set_fill_bitmap_source_basecolor(fill, resource_id)
        fill.set_projection_mode(sp_layerstack.ProjectionMode.Planar)

        anchor = self.build_projection_anchor_for_slot(
            slot_name=slot_name,
            image_path=image_path,
            camera_state=camera_state
        )
        fill.set_projection_parameters(self.make_planar_params_for_slot(slot_name, anchor=anchor))
        return fill

    def create_multiview_projection_group(self, split_tiles, group_name=None):
        if sp_layerstack is None or sp_textureset is None:
            raise RuntimeError("layerstack/textureset API 不可用")

        stack = self.get_active_stack_safe()
        imported_by_slot = {}

        for tile in split_tiles:
            slot_name = tile.get("slot_name", "tile")
            slot_label = tile.get("slot_label", slot_name)
            result_path = tile.get("result_path")
            camera_state = tile.get("camera_state")

            if not result_path or not os.path.exists(result_path):
                continue

            res = self.import_image_as_project_resource(
                image_path=result_path,
                name="ai_mv_{}".format(slot_name),
                group="AIViewToPaint"
            )
            imported_by_slot[slot_name] = {
                "resource": res,
                "slot_label": slot_label,
                "camera_state": camera_state,
                "result_path": result_path,
            }

        if not imported_by_slot:
            raise RuntimeError("没有任何 tile 导入成功")

        created_group = None

        with sp_layerstack.ScopedModification("AI MultiView Projection"):
            group = self.create_group_at_stack_top(
                stack,
                group_name or "AI MultiView {}".format(time.strftime("%H:%M:%S"))
            )
            created_group = group

            for tile in split_tiles:
                slot_name = tile.get("slot_name", "tile")
                slot_label = tile.get("slot_label", slot_name)

                info = imported_by_slot.get(slot_name)
                if not info:
                    continue

                self.create_multiview_fill_layer(
                    parent_group=group,
                    slot_name=slot_name,
                    slot_label=slot_label,
                    resource_id=info["resource"].identifier(),
                    camera_state=info.get("camera_state"),
                    image_path=info.get("result_path")
                )

        return created_group

    def apply_multiview_tiles_to_painter(self, split_tiles, split_manifest_path):
        group = self.create_multiview_projection_group(
            split_tiles=split_tiles,
            group_name="AI MultiView {}".format(time.strftime("%H:%M:%S"))
        )

        self.status_label.setText("多视角投射层已创建")
        self.log("多视角结果已应用到 Painter")
        self.log("切图信息: {}".format(split_manifest_path))
        return group

    def apply_single_result_to_painter(self, record):
        if sp_layerstack is None or sp_textureset is None:
            raise RuntimeError("layerstack/textureset API 不可用")

        result_path = record.get("result_path")
        camera_state = record.get("camera_state")
        if not result_path or not os.path.exists(result_path):
            raise RuntimeError("结果图不存在")
        if not camera_state:
            raise RuntimeError("单视角结果缺少 camera_state")

        stack = self.get_active_stack_safe()
        res = self.import_image_as_project_resource(
            image_path=result_path,
            name="ai_single_{}".format(unique_stamp()),
            group="AIViewToPaint"
        )

        anchor = self.build_projection_anchor_from_camera_state(
            camera_state=camera_state,
            image_path=result_path,
            fallback_slot="front"
        )

        with sp_layerstack.ScopedModification("AI Single Projection"):
            pos = sp_layerstack.InsertPosition.from_textureset_stack(stack)
            fill = sp_layerstack.insert_fill(pos)
            fill.set_name("AI_SingleProjection")
            self.set_fill_bitmap_source_basecolor(fill, res.identifier())
            fill.set_projection_mode(sp_layerstack.ProjectionMode.Planar)
            fill.set_projection_parameters(self.make_planar_params_for_slot("front", anchor=anchor))

        self.status_label.setText("单视角投射层已创建")
        self.log("单视角结果已应用到 Painter")

    def apply_uv_result_to_painter(self, record):
        if sp_layerstack is None or sp_textureset is None:
            raise RuntimeError("layerstack/textureset API 不可用")

        result_path = record.get("result_path")
        if not result_path or not os.path.exists(result_path):
            raise RuntimeError("UV 结果图不存在")

        stack = self.get_active_stack_safe()
        res = self.import_image_as_project_resource(
            image_path=result_path,
            name="ai_uv_{}".format(unique_stamp()),
            group="AIViewToPaint"
        )

        with sp_layerstack.ScopedModification("AI UV Texture"):
            pos = sp_layerstack.InsertPosition.from_textureset_stack(stack)
            fill = sp_layerstack.insert_fill(pos)
            fill.set_name("AI_UVGuideTexture")
            self.set_fill_bitmap_source_basecolor(fill, res.identifier())

            try:
                if hasattr(sp_layerstack, "ProjectionMode") and hasattr(sp_layerstack.ProjectionMode, "UV"):
                    fill.set_projection_mode(sp_layerstack.ProjectionMode.UV)
            except Exception:
                pass

        self.status_label.setText("UV 贴图层已创建")
        self.log("UV 结果已作为 UV 贴图应用到 Painter")

    def apply_normal_result_to_painter(self, record):
        if sp_layerstack is None or sp_textureset is None:
            raise RuntimeError("layerstack/textureset API 不可用")

        result_path = record.get("result_path")
        if not result_path or not os.path.exists(result_path):
            raise RuntimeError("法线结果图不存在")

        stack = self.get_active_stack_safe()
        res = self.import_image_as_project_resource(
            image_path=result_path,
            name="ai_normal_{}".format(unique_stamp()),
            group="AIViewToPaint"
        )

        with sp_layerstack.ScopedModification("AI Normal Texture"):
            pos = sp_layerstack.InsertPosition.from_textureset_stack(stack)
            fill = sp_layerstack.insert_fill(pos)
            fill.set_name("AI_NormalTexture")
            self.set_fill_bitmap_source_normal(fill, res.identifier())

            try:
                if hasattr(sp_layerstack, "ProjectionMode") and hasattr(sp_layerstack.ProjectionMode, "UV"):
                    fill.set_projection_mode(sp_layerstack.ProjectionMode.UV)
            except Exception:
                pass

        self.status_label.setText("法线贴图层已创建")
        self.log("法线结果已应用到 Painter")

    def apply_payload_internal(self, payload):
        if payload.get("mode") == MODE_MULTI:
            result_path = payload.get("result_path")
            manifest = payload.get("manifest")

            if not result_path or not os.path.exists(result_path):
                raise RuntimeError("多视角结果图不存在")
            if not isinstance(manifest, dict):
                raise RuntimeError("多视角 manifest 不存在")

            split_dir = os.path.splitext(result_path)[0] + "_tiles"
            split_tiles, split_manifest_path = split_multiview_result_by_manifest(
                result_image_path=result_path,
                manifest=manifest,
                output_dir=split_dir
            )

            self.log("多视角结果已切图，共 {} 张".format(len(split_tiles)))
            self.apply_multiview_tiles_to_painter(split_tiles, split_manifest_path)

        elif payload.get("mode") == "uv_texture":
            self.apply_uv_result_to_painter(payload.get("record") or {})

        elif payload.get("mode") == "normal_texture":
            self.apply_normal_result_to_painter(payload.get("record") or {})

        else:
            self.apply_single_result_to_painter(payload.get("record") or {})

    def _safe_apply_payload(self, payload):
        try:
            self.pending_apply_payload = None
            self.apply_btn.setEnabled(False)

            self.apply_payload_internal(payload)
            self.refresh_apply_button_from_selection()

        except Exception as e:
            self.log(traceback.format_exc())
            self.pending_apply_payload = payload
            self.apply_btn.setEnabled(True)
            self.preview_tabs.setCurrentWidget(self.log_page)
            self.set_status("应用到 Painter 失败: {}".format(e))

    def on_apply_clicked(self):
        if not self.pending_apply_payload:
            current_item = self.result_list.currentItem()
            if current_item is not None:
                record = current_item.data(QtCore.Qt.ItemDataRole.UserRole) or {}
                self.pending_apply_payload = self.build_apply_payload_from_result_record(record)

        if not self.pending_apply_payload:
            self.status_label.setText("当前没有可应用的数据")
            return

        self._safe_apply_payload(dict(self.pending_apply_payload))

    def on_open_dir_clicked(self):
        try:
            output_dir = self.current_output_dir(create=True)
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(output_dir))
            self.log("已打开输出目录: {}".format(output_dir))
            self.status_label.setText("已打开输出目录")
        except Exception as e:
            self.log(traceback.format_exc())
            self.preview_tabs.setCurrentWidget(self.log_page)
            self.set_status("打开目录失败: {}".format(e))

    def on_output_dir_changed(self):
        self.persist_output_dir_setting()
        self.clear_preview()
        self.reload_galleries(log_message=True)

    def on_image_size_changed(self, text):
        self.settings_data = merge_plugin_settings(dict(self.settings_data, **{
            "default_image_size": (text or "").strip() or DEFAULT_IMAGE_SIZE
        }))
        save_plugin_settings(self.settings_data)

    def cleanup(self):
        self.gen_cancel_requested = True
        self.gen_running = False
        try:
            self.gen_poll_timer.stop()
        except Exception:
            pass

    def closeEvent(self, event):
        try:
            self.cleanup()
        except Exception:
            pass
        super().closeEvent(event)


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
