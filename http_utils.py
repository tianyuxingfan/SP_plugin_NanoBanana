# -*- coding: utf-8 -*-
"""http_utils module - split from AI_View_To_Paint.py (auto-generated)."""
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
from ai_view_to_paint import config
from ai_view_to_paint.log_utils import log_debug, log_error, short_json, short_text
from ai_view_to_paint.utils import sanitize_headers, ssl_context

def http_post_json(url, headers, payload, timeout=120):
    data = json.dumps(payload).encode("utf-8")
    safe_headers = sanitize_headers(headers)

    log_debug("HTTP", "POST {} headers={}".format(url, short_json(safe_headers, 240)))
    log_debug("HTTP", "POST {} payload={}".format(url, short_json(payload, 400)))

    req = urllib.request.Request(url=url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:
            status_code = resp.getcode()
            body = resp.read()
            text = body.decode("utf-8", errors="replace")

            log_debug("HTTP", "POST {} -> status={}".format(url, status_code))
            if config.ENABLE_HTTP_DEBUG_BODY:
                log_debug("HTTP", "POST {} response={}".format(url, short_text(text, 1200)))

            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            return status_code, text, parsed

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        log_error("HTTP", "POST {} -> HTTPError {} body={}".format(
            url, e.code, short_text(body, 600)
        ))
        raise RuntimeError("HTTPError {}: {}".format(e.code, body))

    except urllib.error.URLError as e:
        log_error("HTTP", "POST {} -> URLError {}".format(url, repr(e)))
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

    debug_files = []
    for f in (files or []):
        debug_files.append({
            "name": f.get("name"),
            "filename": f.get("filename"),
            "content_type": f.get("content_type"),
            "bytes": len(f.get("content", b"") or b"")
        })

    log_debug("HTTP", "MULTIPART POST {} headers={}".format(
        url, short_json(sanitize_headers(req_headers), 240)
    ))
    log_debug("HTTP", "MULTIPART POST {} files={}".format(
        url, short_json(debug_files, 400)
    ))

    req = urllib.request.Request(url=url, data=bytes(body), headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:
            status_code = resp.getcode()
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")

            log_debug("HTTP", "MULTIPART POST {} -> status={}".format(url, status_code))
            if config.ENABLE_HTTP_DEBUG_BODY:
                log_debug("HTTP", "MULTIPART POST {} response={}".format(url, short_text(text, 1200)))

            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            return status_code, text, parsed
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        log_error("HTTP", "MULTIPART POST {} -> HTTPError {} body={}".format(
            url, e.code, short_text(body, 600)
        ))
        raise RuntimeError("HTTPError {}: {}".format(e.code, body))
    except urllib.error.URLError as e:
        log_error("HTTP", "MULTIPART POST {} -> URLError {}".format(url, repr(e)))
        raise RuntimeError("URLError: {}".format(e))


def http_get_json(url, headers=None, timeout=120):
    req_headers = dict(headers or {})

    log_debug("HTTP", "GET {} headers={}".format(
        url,
        short_json(sanitize_headers(req_headers), 240)
    ))

    req = urllib.request.Request(url=url, headers=req_headers, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:
            status_code = resp.getcode()
            body = resp.read()
            text = body.decode("utf-8", errors="replace")

            log_debug("HTTP", "GET {} -> status={}".format(url, status_code))
            if config.ENABLE_HTTP_DEBUG_BODY:
                log_debug("HTTP", "GET {} response={}".format(url, short_text(text, 1200)))

            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None

            return status_code, text, parsed

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        log_error("HTTP", "GET {} -> HTTPError {} body={}".format(
            url, e.code, short_text(body, 600)
        ))
        raise RuntimeError("HTTPError {}: {}".format(e.code, body))

    except urllib.error.URLError as e:
        log_error("HTTP", "GET {} -> URLError {}".format(url, repr(e)))
        raise RuntimeError("URLError: {}".format(e))


def http_get_bytes(url, timeout=120):
    req = urllib.request.Request(url=url, method="GET")
    log_debug("HTTP", "GET {}".format(url))
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:
            data = resp.read()
            log_debug("HTTP", "GET {} -> {} bytes".format(url, len(data)))
            return data
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        log_error("HTTP", "GET {} -> HTTPError {} body={}".format(
            url, e.code, short_text(body, 600)
        ))
        raise RuntimeError("HTTPError {}: {}".format(e.code, body))
    except urllib.error.URLError as e:
        log_error("HTTP", "GET {} -> URLError {}".format(url, repr(e)))
        raise RuntimeError("URLError: {}".format(e))
