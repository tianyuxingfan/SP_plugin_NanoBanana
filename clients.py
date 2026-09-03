# -*- coding: utf-8 -*-
"""clients module - split from AI_View_To_Paint.py (auto-generated)."""
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
from ai_view_to_paint.config import DEFAULT_IMAGE_SIZE, DEFAULT_POLL_INTERVAL, DEFAULT_POLL_TIMEOUT, PROVIDER_GRSAI, PROVIDER_RUNNINGHUB, RESULT_PATH, RUNNINGHUB_API_BASE, RUNNINGHUB_DEFAULT_SUBMIT_PATH, RUNNINGHUB_MAX_IMAGES_DEFAULT, RUNNINGHUB_MAX_IMAGES_OFFICIAL, RUNNINGHUB_RESULT_PATH, RUNNINGHUB_TEXT_PATH, RUNNINGHUB_UPLOAD_BINARY, RUNNINGHUB_UPLOAD_DATA_URI, RUNNINGHUB_UPLOAD_PATH, SUBMIT_PATH
from ai_view_to_paint.http_utils import http_get_bytes, http_get_json, http_post_json, http_post_multipart
from ai_view_to_paint.log_utils import log_debug, log_info, short_json, short_text
from ai_view_to_paint.utils import merge_plugin_settings, parse_sse_data_json_lines, read_binary

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
        self._stream_result_cache = {}

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

    def is_gpt_image_model(self, model):
        return str(model or "").strip().lower() in ("gpt-image-2", "gpt-image-2-vip")

    def get_submit_path_by_model(self, model):
        return self.submit_path

    def normalize_gpt_image_aspect_ratio_pixels(self, aspect_ratio, image_size="1K", model="gpt-image-2"):
        ratio = str(aspect_ratio or "").strip().lower()
        size = str(image_size or "").strip().upper()
        model = str(model or "").strip().lower()

        if not ratio or ratio == "auto":
            ratio = "1:1"

        is_vip = model == "gpt-image-2-vip"

        table_1k = {
            "1:1": "1024x1024",
            "16:9": "1774x887",
            "9:16": "887x1774",
            "3:2": "1536x1024",
            "2:3": "1024x1536",
            "21:9": "2048x880",
            "9:21": "880x2048",
            "1:3": "688x2048",
            "3:1": "2048x688",
            "2:1": "2048x1024",
            "1:2": "1024x2048",
            "4:3": "1365x1024",
            "3:4": "1024x1365",
            "5:4": "1280x1024",
            "4:5": "1024x1280",
        }

        table_2k = {
            "1:1": "2048x2048",
            "16:9": "2048x1152",
            "9:16": "1152x2048",
            "3:2": "2048x1360",
            "2:3": "1360x2048",
            "21:9": "2048x880",
            "9:21": "880x2048",
            "1:3": "688x2048",
            "3:1": "2048x688",
            "2:1": "2048x1024",
            "1:2": "1024x2048",
            "4:3": "2048x1536",
            "3:4": "1536x2048",
            "5:4": "2048x1638",
            "4:5": "1638x2048",
        }

        table_4k = {
            "1:1": "2880x2880",
            "16:9": "3840x2160",
            "9:16": "2160x3840",
            "3:2": "3504x2336",
            "2:3": "2336x3504",
            "21:9": "3840x1648",
            "9:21": "1648x3840",
            "1:3": "1280x3840",
            "3:1": "3840x1280",
            "2:1": "3840x1920",
            "1:2": "1920x3840",
            "4:3": "3840x2880",
            "3:4": "2880x3840",
            "5:4": "3840x3072",
            "4:5": "3072x3840",
        }

        if not is_vip:
            return table_1k.get(ratio, "1024x1024")

        if size == "4K":
            return table_4k.get(ratio, "2880x2880")
        if size == "2K":
            return table_2k.get(ratio, "2048x2048")
        return table_1k.get(ratio, "1024x1024")

    def normalize_aspect_ratio_for_gpt_image(self, aspect_ratio):
        text = str(aspect_ratio or "").strip().lower()
        allowed = {
            "auto", "1:1", "3:2", "2:3", "16:9", "9:16",
            "5:4", "4:5", "4:3", "3:4", "21:9", "9:21",
            "1:3", "3:1", "2:1", "1:2"
        }
        if text in allowed:
            return text
        return "auto"

    def prepare_upload_image_bytes_and_mime(self, image_path, max_side=1536):
        try:
            image = QtGui.QImage(image_path)
            if image.isNull():
                ext = os.path.splitext(image_path)[1].lower()
                mime = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                    ".bmp": "image/bmp",
                }.get(ext, "application/octet-stream")
                return read_binary(image_path), mime

            src_w = image.width()
            src_h = image.height()
            if src_w <= 0 or src_h <= 0:
                return read_binary(image_path), "application/octet-stream"

            max_side = max(256, int(max_side))

            if max(src_w, src_h) <= max_side:
                ext = os.path.splitext(image_path)[1].lower()
                mime = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                    ".bmp": "image/bmp",
                }.get(ext, "image/png")
                return read_binary(image_path), mime

            scaled = image.scaled(
                QtCore.QSize(max_side, max_side),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation
            )

            has_alpha = scaled.hasAlphaChannel()

            byte_array = QtCore.QByteArray()
            buffer = QtCore.QBuffer(byte_array)
            buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)

            if has_alpha:
                ok = scaled.save(buffer, "PNG")
                mime = "image/png"
            else:
                ok = scaled.save(buffer, "JPG", quality=92)
                mime = "image/jpeg"

            buffer.close()

            if ok and not byte_array.isEmpty():
                return bytes(byte_array), mime

        except Exception:
            pass

        ext = os.path.splitext(image_path)[1].lower()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }.get(ext, "application/octet-stream")
        return read_binary(image_path), mime

    def get_upload_max_side(self, image_path=None):
        return 1536

    def image_file_to_base64(self, image_path, force_data_url_prefix=None):
        max_side = self.get_upload_max_side(image_path)
        data, mime = self.prepare_upload_image_bytes_and_mime(image_path, max_side=max_side)
        b64 = base64.b64encode(data).decode("utf-8")

        log_debug("API", "GRSAI encode image={} mime={} bytes={} max_side={}".format(
            os.path.basename(str(image_path or "")),
            mime,
            len(data),
            max_side
        ))

        if force_data_url_prefix is None:
            use_prefix = self.use_data_url_prefix
        else:
            use_prefix = bool(force_data_url_prefix)

        if use_prefix:
            return "data:{};base64,{}".format(mime, b64)

        return b64

    def submit_task_common(self, prompt, model, aspect_ratio, image_size, urls=None, shut_progress=True,
                           cancel_cb=None):
        if cancel_cb and cancel_cb():
            raise RuntimeError("已取消")

        model = str(model or "").strip()
        url = self.api_base + self.submit_path

        images = list(urls or [])

        if self.is_gpt_image_model(model):
            payload = {
                "model": model,
                "prompt": prompt,
                "images": images,
                "aspectRatio": self.normalize_gpt_image_aspect_ratio_pixels(
                    aspect_ratio=aspect_ratio,
                    image_size=image_size,
                    model=model
                ),
                "replyType": "async"
            }
        else:
            payload = {
                "model": model,
                "prompt": prompt,
                "images": images,
                "aspectRatio": str(aspect_ratio or "auto").strip() or "auto",
                "imageSize": str(image_size or DEFAULT_IMAGE_SIZE).strip().upper(),
                "replyType": "async"
            }

        log_info("API", "提交任务: provider=grsai model={} images={}".format(model, len(images)))
        log_debug("API", "GRSAI submit url={} payload={}".format(
            url,
            short_json(payload, 500)
        ))

        _, text, data = http_post_json(
            url=url,
            headers=self._headers(),
            payload=payload,
            timeout=max(120, int(self.poll_timeout))
        )

        if cancel_cb and cancel_cb():
            raise RuntimeError("已取消")

        if isinstance(data, dict):
            status = str(data.get("status", "") or "").strip().lower()

            if status in ("failed", "violation"):
                raise RuntimeError("提交失败: {}".format(json.dumps(data, ensure_ascii=False)))

            task_id = str(data.get("id", "") or "").strip()
            if not task_id:
                raise RuntimeError("提交成功但缺少 id: {}".format(text))

            if status == "succeeded":
                results = data.get("results", []) or []
                if results:
                    image_url = str((results[0] or {}).get("url", "") or "").strip()
                    if image_url:
                        self._stream_result_cache[task_id] = image_url

            log_debug("API", "GRSAI 提交成功: task_id={} status={}".format(task_id, status))
            return task_id

        events = parse_sse_data_json_lines(text)
        if events:
            first = events[0] or {}
            last = events[-1] or {}

            task_id = str(first.get("id") or last.get("id") or "").strip()
            if not task_id:
                raise RuntimeError("提交返回 stream，但缺少 id: {}".format(short_text(text, 1000)))

            status = str(last.get("status", "") or "").strip().lower()

            if status in ("failed", "violation"):
                error = last.get("error", "")
                failure_reason = last.get("failure_reason", "")
                raise RuntimeError(
                    "提交失败: status={}, failure_reason={}, error={}, raw={}".format(
                        status,
                        failure_reason,
                        error,
                        json.dumps(last, ensure_ascii=False)
                    )
                )

            if status == "succeeded":
                results = last.get("results", []) or []
                if results:
                    image_url = str((results[0] or {}).get("url", "") or "").strip()
                    if image_url:
                        self._stream_result_cache[task_id] = image_url
                        log_debug("API", "GRSAI stream 已完成，缓存结果 url: task_id={}".format(task_id))

            log_debug("API", "GRSAI stream 提交成功: task_id={} status={}".format(task_id, status))
            return task_id

        raise RuntimeError("提交接口返回不是 JSON，也不是可解析的 stream: {}".format(short_text(text, 1200)))

    def submit_task_multi(self, image_paths, prompt, model, aspect_ratio, image_size, shut_progress=True,
                          cancel_cb=None):
        urls = []

        force_data_url = self.is_gpt_image_model(model)

        for image_path in (image_paths or []):
            if cancel_cb and cancel_cb():
                raise RuntimeError("已取消")
            urls.append(self.image_file_to_base64(
                image_path,
                force_data_url_prefix=force_data_url
            ))

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
        image_b64 = self.image_file_to_base64(
            image_path,
            force_data_url_prefix=self.is_gpt_image_model(model)
        )

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

        from urllib.parse import urlencode

        query = urlencode({
            "id": task_id
        })

        url = self.api_base + self.result_path + "?" + query

        log_debug("API", "GRSAI query_result task_id={}".format(task_id))

        _, text, data = http_get_json(
            url=url,
            headers=self._headers(),
            timeout=20
        )

        if cancel_cb and cancel_cb():
            raise RuntimeError("已取消")

        if not isinstance(data, dict):
            raise RuntimeError("结果接口返回不是 JSON: {}".format(text))

        return data

    def poll_result_url(self, task_id, progress_cb=None, cancel_cb=None):
        cached_url = None
        try:
            cached_url = self._stream_result_cache.pop(task_id, None)
        except Exception:
            cached_url = None

        if cached_url:
            if progress_cb:
                progress_cb("任务已通过 stream 完成")
            return cached_url

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

            status = str(data.get("status", "") or "").strip().lower()
            progress = data.get("progress", 0)

            if progress_cb:
                progress_cb("任务中... status={} progress={}%".format(status or "unknown", progress))

            if status == "succeeded":
                results = data.get("results", [])
                if not results:
                    raise RuntimeError("任务成功，但 results 为空: {}".format(
                        json.dumps(data, ensure_ascii=False)
                    ))

                first = results[0] or {}
                image_url = str(first.get("url", "") or "").strip()
                if not image_url:
                    raise RuntimeError("任务成功，但 results[0].url 为空: {}".format(
                        json.dumps(data, ensure_ascii=False)
                    ))

                return image_url

            if status in ("failed", "violation"):
                error = data.get("error", "")
                raise RuntimeError(
                    "生成失败: status={}, error={}, raw={}".format(
                        status,
                        error,
                        json.dumps(data, ensure_ascii=False)
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
        text_submit_path=RUNNINGHUB_TEXT_PATH,
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
        self.text_submit_path = (str(text_submit_path or "").strip() or RUNNINGHUB_TEXT_PATH)
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

    def prepare_upload_image_bytes_and_mime(self, image_path, max_side=1536):
        try:
            image = QtGui.QImage(image_path)
            if image.isNull():
                ext = os.path.splitext(image_path)[1].lower()
                mime = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                    ".bmp": "image/bmp",
                }.get(ext, "application/octet-stream")
                return read_binary(image_path), mime

            src_w = image.width()
            src_h = image.height()
            if src_w <= 0 or src_h <= 0:
                return read_binary(image_path), "application/octet-stream"

            max_side = max(256, int(max_side))

            if max(src_w, src_h) <= max_side:
                ext = os.path.splitext(image_path)[1].lower()
                mime = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                    ".bmp": "image/bmp",
                }.get(ext, "image/png")
                return read_binary(image_path), mime

            scaled = image.scaled(
                QtCore.QSize(max_side, max_side),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation
            )

            has_alpha = scaled.hasAlphaChannel()

            byte_array = QtCore.QByteArray()
            buffer = QtCore.QBuffer(byte_array)
            buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)

            if has_alpha:
                ok = scaled.save(buffer, "PNG")
                mime = "image/png"
            else:
                ok = scaled.save(buffer, "JPG", quality=92)
                mime = "image/jpeg"

            buffer.close()

            if ok and not byte_array.isEmpty():
                return bytes(byte_array), mime

        except Exception:
            pass

        ext = os.path.splitext(image_path)[1].lower()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }.get(ext, "application/octet-stream")
        return read_binary(image_path), mime

    def get_upload_max_side(self, image_path=None):
        return 1536

    def image_file_to_data_uri(self, image_path):
        data, mime = self.prepare_upload_image_bytes_and_mime(
            image_path,
            max_side=self.get_upload_max_side(image_path)
        )
        b64 = base64.b64encode(data).decode("utf-8")
        return "data:{};base64,{}".format(mime, b64)

    def upload_binary_and_get_url(self, image_path):
        url = self.api_base + self.upload_path
        filename = os.path.basename(image_path)
        data, mime = self.prepare_upload_image_bytes_and_mime(
            image_path,
            max_side=self.get_upload_max_side(image_path)
        )

        log_info("API", "RunningHub 上传图片: {}".format(filename))
        log_debug("API", "RunningHub upload mime={} bytes={}".format(mime, len(data)))

        _, text, data = http_post_multipart(
            url=url,
            headers=self._headers(include_content_type=False),
            files=[{
                "name": "file",
                "filename": filename,
                "content": data,
                "content_type": mime,
            }],
            timeout=60
        )

        if not isinstance(data, dict):
            raise RuntimeError("RunningHub 上传返回不是 JSON: {}".format(text))

        # 国内站(runninghub.cn)返回 code=0，国际站(runninghub.ai)文档示例为 code=200
        if data.get("code") not in (0, 200):
            raise RuntimeError("RunningHub 上传失败: {}".format(text))

        data_obj = data.get("data") or {}
        download_url = str(data_obj.get("download_url", "") or "").strip()
        if not download_url:
            raise RuntimeError("RunningHub 上传成功但缺少 data.download_url: {}".format(text))

        log_info("API", "RunningHub 上传成功")
        log_debug("API", "RunningHub upload url={}".format(download_url))
        return download_url

    def _map_aspect_ratio(self, aspect_ratio):
        text = str(aspect_ratio or "").strip().lower()
        if not text:
            return "auto"

        # 官方枚举值：1:1 2:3 3:2 3:4 4:3 4:5 5:4 16:9 9:16 21:9
        # 官方稳定版不传该参数时为自适应；"auto" 时也不发送该字段
        allowed = {
            "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4",
            "16:9", "9:16", "21:9",
        }
        if text in allowed:
            return text
        return "auto"

    def get_max_image_urls(self):
        # 官方稳定版接口最多14张参考图，其他渠道（如低价渠道版）最多10张
        path = str(self.submit_path or "").lower()
        if "-official" in path:
            return RUNNINGHUB_MAX_IMAGES_OFFICIAL
        return RUNNINGHUB_MAX_IMAGES_DEFAULT

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

    def generate_from_prompt(self, prompt, model, aspect_ratio, image_size, shut_progress=True, progress_cb=None,
                             cancel_cb=None):
        if not self.api_key:
            raise RuntimeError("API Key 为空")

        # 提示词生成模式走文生图端点（无 imageUrls）
        task_id = self.submit_task_common(
            prompt=prompt,
            model=model,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            image_urls=None,
            shut_progress=shut_progress,
            cancel_cb=cancel_cb,
            submit_path=self.text_submit_path,
        )

        if progress_cb:
            progress_cb("任务已提交，ID={}".format(task_id))

        image_url = self.poll_result_url(task_id, progress_cb=progress_cb, cancel_cb=cancel_cb)

        if progress_cb:
            progress_cb("结果已完成，正在下载图片...")

        return self.download_image(image_url, cancel_cb=cancel_cb)

    def submit_task_common(self, prompt, model, aspect_ratio, image_size, image_urls=None, shut_progress=True,
                           cancel_cb=None, submit_path=None):
        if cancel_cb and cancel_cb():
            raise RuntimeError("已取消")

        payload = {
            "prompt": prompt,
            "resolution": self._map_resolution(image_size),
        }

        # 官方稳定版 aspectRatio 枚举无 "auto"（不传该参数时为自适应），因此 auto 时不发送
        aspect = self._map_aspect_ratio(aspect_ratio)
        if aspect != "auto":
            payload["aspectRatio"] = aspect

        if image_urls:
            max_images = self.get_max_image_urls()
            if len(image_urls) > max_images:
                raise RuntimeError(
                    "RunningHub 参考图数量超过上限：当前 {} 张，最多 {} 张（官方稳定版最多 {} 张），请减少参考图数量".format(
                        len(image_urls), max_images, RUNNINGHUB_MAX_IMAGES_OFFICIAL
                    )
                )
            payload["imageUrls"] = image_urls

        url = self.api_base + (submit_path or self.submit_path)

        log_info("API", "提交任务: provider=runninghub images={}".format(len(image_urls or [])))
        log_debug("API", "RunningHub submit url={} size={} aspect={}".format(
            url,
            self._map_resolution(image_size),
            aspect
        ))

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

        log_debug("API", "RunningHub 提交成功: task_id={}".format(task_id))
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

        log_debug("API", "RunningHub query_result task_id={}".format(task_id))

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
            text_submit_path=s.get("runninghub_text_path", RUNNINGHUB_TEXT_PATH),
            poll_interval=s["poll_interval"],
            poll_timeout=s["poll_timeout"],
            auth_mode=s["auth_mode"],
            upload_mode=s["runninghub_upload_mode"],
        )

    raise RuntimeError("不支持的平台类型: {}".format(provider))
