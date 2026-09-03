# -*- coding: utf-8 -*-
"""config module - split from AI_View_To_Paint.py (auto-generated)."""
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


SUBMIT_PATH = "/v1/api/generate"


RESULT_PATH = "/v1/api/result"


DEFAULT_MODEL = "nano-banana-2"


DEFAULT_ASPECT_RATIO = "auto"


DEFAULT_IMAGE_SIZE = "2K"


ALLOWED_MODELS = [
    "nano-banana-2",
    "nano-banana-pro",
    "gpt-image-2",
    "gpt-image-2-vip",
]


DEFAULT_POLL_INTERVAL = 1.5


DEFAULT_POLL_TIMEOUT = 300


DEFAULT_OUTPUT_DIR = os.path.expanduser("~/Pictures/sp_ai_outputs")


PROVIDER_GRSAI = "grsai"


PROVIDER_RUNNINGHUB = "runninghub"


RUNNINGHUB_API_BASE = "https://www.runninghub.cn"


# 全能图片V2-图生图-官方稳定版（支持最多14张参考图、4K输出）
# 官方文档: https://www.runninghub.cn/runninghub-api-doc-cn/api-448183224
RUNNINGHUB_DEFAULT_SUBMIT_PATH = "/openapi/v2/rhart-image-n-g31-flash-official/image-to-image"


# 全能图片V2-文生图-官方稳定版（用于提示词生成模式）
RUNNINGHUB_TEXT_PATH = "/openapi/v2/rhart-image-n-g31-flash-official/text-to-image"


# 旧的默认提交路径（低价渠道版，官方标注不稳定），保留用于自动迁移
RUNNINGHUB_LEGACY_SUBMIT_PATH = "/openapi/v2/rhart-image-n-g31-flash/image-to-image"


# imageUrls 数量上限：官方稳定版最多14张，其他渠道（如低价渠道版）最多10张
RUNNINGHUB_MAX_IMAGES_OFFICIAL = 14

RUNNINGHUB_MAX_IMAGES_DEFAULT = 10


RUNNINGHUB_RESULT_PATH = "/openapi/v2/query"


RUNNINGHUB_UPLOAD_PATH = "/openapi/v2/media/upload/binary"


RUNNINGHUB_UPLOAD_DATA_URI = "data_uri"


RUNNINGHUB_UPLOAD_BINARY = "upload_binary"


PROVIDER_PRESETS = {
    PROVIDER_GRSAI: {
        "label": "GRSAI",
        "api_base": "https://grsai.dakka.com.cn",
        "submit_path": "/v1/api/generate",
        "result_path": "/v1/api/result",
        "auth_mode": "bearer",
    },
    PROVIDER_RUNNINGHUB: {
        "label": "RunningHub",
        "api_base": RUNNINGHUB_API_BASE,
        "submit_path": RUNNINGHUB_DEFAULT_SUBMIT_PATH,
        "result_path": RUNNINGHUB_RESULT_PATH,
        "text_submit_path": RUNNINGHUB_TEXT_PATH,
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
    "runninghub_text_path": RUNNINGHUB_TEXT_PATH,

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


DEFAULT_MULTI_PROMPT = """根据当前模型视角图生成贴图效果，保持主体结构、轮廓、视角与构图一致。

要求：
1. 严格保持当前视角的结构、轮廓与构图不变
2. 材质、配色与细节风格保持统一协调
3. 不改变主体比例，不新增或删减主体结构

材质指定："""


DEFAULT_MULTI_REF_PROMPT = """参考输入中的参考图风格与材质表现，重绘当前模型视角图。

要求：
1. 严格保持当前模型视角图的结构、轮廓、视角与构图不变
2. 参考参考图的材质、配色、细节和风格
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


LOG_DEBUG = 10


LOG_INFO = 20


LOG_WARN = 30


LOG_ERROR = 40


DEFAULT_LOG_LEVEL = LOG_INFO


ENABLE_HTTP_DEBUG_BODY = False
