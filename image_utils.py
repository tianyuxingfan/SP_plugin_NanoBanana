# -*- coding: utf-8 -*-
"""image_utils module - split from AI_View_To_Paint.py (auto-generated)."""
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
from ai_view_to_paint.config import DEFAULT_ATLAS_BG, DEFAULT_MULTI_TILE_SIZE, MULTIVIEW_MAX_UPSCALE, MULTIVIEW_PACK_GAP, MULTIVIEW_PACK_OUTER_PADDING, MULTIVIEW_PACK_SIDE_4, MULTIVIEW_PACK_SIDE_6, MULTIVIEW_SUBJECT_BG_TOLERANCE, MULTIVIEW_SUBJECT_PADDING, MULTIVIEW_SUBJECT_SAMPLE_STEP, MULTIVIEW_VIEWPORT_TRIM_BOTTOM, MULTIVIEW_VIEWPORT_TRIM_LEFT, MULTIVIEW_VIEWPORT_TRIM_RIGHT, MULTIVIEW_VIEWPORT_TRIM_TOP
from ai_view_to_paint.utils import now_str_readable

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


def _detect_letterbox_from_pixels(w, h, get_rgb, color_tol=20, min_bar_px=3, max_scan_ratio=0.45):
    """按像素访问器检测结果图四边的 letterbox 灰边。

    返回内容区 (left, top, right, bottom)；四边均无有效灰边时返回 None。
    """
    if w < 8 or h < 8:
        return None

    # 边框色取四角平均（AI 通常会近似还原 #242424 补边，颜色允许有偏差）
    corners = [get_rgb(1, 1), get_rgb(w - 2, 1), get_rgb(1, h - 2), get_rgb(w - 2, h - 2)]
    br = sum(c[0] for c in corners) // len(corners)
    bg = sum(c[1] for c in corners) // len(corners)
    bb = sum(c[2] for c in corners) // len(corners)

    def bar_pixel(x, y):
        r, g, b = get_rgb(x, y)
        return (abs(r - br) <= color_tol and
                abs(g - bg) <= color_tol and
                abs(b - bb) <= color_tol)

    step = max(1, min(w, h) // 512)

    def row_is_bar(y):
        for x in range(0, w, step):
            if not bar_pixel(x, y):
                return False
        return True

    def col_is_bar(x):
        for y in range(0, h, step):
            if not bar_pixel(x, y):
                return False
        return True

    max_rows = max(min_bar_px, int(h * max_scan_ratio))
    max_cols = max(min_bar_px, int(w * max_scan_ratio))

    top = 0
    while top < max_rows and row_is_bar(top):
        top += 1

    bottom = h
    while h - bottom < max_rows and row_is_bar(bottom - 1):
        bottom -= 1

    left = 0
    while left < max_cols and col_is_bar(left):
        left += 1

    right = w
    while w - right < max_cols and col_is_bar(right - 1):
        right -= 1

    # 小于最小厚度的边视为没有灰边
    if top < min_bar_px:
        top = 0
    if h - bottom < min_bar_px:
        bottom = h
    if left < min_bar_px:
        left = 0
    if w - right < min_bar_px:
        right = w

    if top <= 0 and bottom >= h and left <= 0 and right >= w:
        return None

    return (left, top, right, bottom)


def detect_letterbox_rect(image, color_tol=20, min_bar_px=3, max_scan_ratio=0.45):
    """检测结果图（QImage）四边的 letterbox 灰边，返回内容区 (left, top, right, bottom)。

    输入是带 #242424 灰边的方形图时，AI 结果通常会（近似）还原灰边布局；
    若 AI 未还原灰边（直接返回内容）或改变了构图，则检测不到灰边。
    """
    if image is None or image.isNull():
        return None

    img = image.convertToFormat(QtGui.QImage.Format.Format_ARGB32)
    if img is None or img.isNull():
        return None

    w = img.width()
    h = img.height()

    def get_rgb(x, y):
        v = img.pixel(x, y)
        return (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF

    return _detect_letterbox_from_pixels(
        w, h, get_rgb,
        color_tol=color_tol, min_bar_px=min_bar_px, max_scan_ratio=max_scan_ratio
    )


def _manifest_scaled_rect(manifest, dst_w, dst_h):
    """按 manifest 的 content_rect 推算结果图中的期望内容区 (x0, y0, x1, y1)。"""
    output_size = manifest.get("output_size", [])
    content_rect = manifest.get("content_rect", [])

    if len(output_size) != 2 or len(content_rect) != 4:
        return None

    src_w, src_h = int(output_size[0]), int(output_size[1])
    rx, ry, rw, rh = [int(v) for v in content_rect]

    if src_w <= 0 or src_h <= 0 or dst_w <= 0 or dst_h <= 0:
        return None

    scale_x = float(dst_w) / float(src_w)
    scale_y = float(dst_h) / float(src_h)

    x0 = int(round(rx * scale_x))
    y0 = int(round(ry * scale_y))
    x1 = int(round((rx + rw) * scale_x))
    y1 = int(round((ry + rh) * scale_y))

    x0 = max(0, min(x0, dst_w - 1))
    y0 = max(0, min(y0, dst_h - 1))
    x1 = max(x0 + 1, min(x1, dst_w))
    y1 = max(y0 + 1, min(y1, dst_h))

    return (x0, y0, x1, y1)


def _union_rect(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _choose_crop_rect(dst_w, dst_h, manifest_rect, detected_rect):
    """选定最终裁切区，保证不裁进主体内容。

    策略：
    1. 检测到灰边：取 检测内容区 ∪ manifest 期望区（并集只会多裁灰边/背景，
       不会裁掉物体；manifest 同时兜住"检测把深色背景误判为灰边"的过裁）
    2. 检测不到灰边 + 方形输出：大概率保持了布局但灰边被重绘得不均匀，用 manifest
    3. 其余：保留整图（AI 直接返回内容/改变构图时，避免按 manifest 裁掉物体）

    返回 (rect, mode)，mode ∈ {"detected", "manifest", "full"}
    """
    if detected_rect is not None:
        dx0, dy0, dx1, dy1 = detected_rect
        if (dx1 - dx0) >= dst_w * 0.2 and (dy1 - dy0) >= dst_h * 0.2:
            # 检测内容区过小时视为误检，走后续兜底
            return _union_rect(detected_rect, manifest_rect), "detected"

    if manifest_rect is not None:
        aspect = float(dst_w) / float(dst_h)
        if abs(aspect - 1.0) <= 0.03:
            return manifest_rect, "manifest"

    return (0, 0, dst_w, dst_h), "full"


def split_single_result_by_manifest(result_image_path, manifest, output_path, image=None):
    """裁掉结果图的 letterbox 灰边，恢复视口真实比例。

    裁切区优先按"实际检测到的灰边 ∪ manifest 期望区"选取，避免 AI 未还原
    灰边或改变构图时把物体裁掉。可通过 image 参数直接传入内存中的 QImage，
    避免 result_image_path 必须先落盘。
    """
    if not isinstance(manifest, dict):
        raise RuntimeError("single_view manifest 无效")

    if image is None:
        image = QtGui.QImage(result_image_path)
    if image is None or image.isNull():
        raise RuntimeError("无法读取结果图: {}".format(result_image_path))

    dst_w = image.width()
    dst_h = image.height()

    if dst_w <= 0 or dst_h <= 0:
        raise RuntimeError("结果尺寸无效")

    manifest_rect = _manifest_scaled_rect(manifest, dst_w, dst_h)
    detected_rect = detect_letterbox_rect(image)
    rect, mode = _choose_crop_rect(dst_w, dst_h, manifest_rect, detected_rect)

    x0, y0, x1, y1 = rect
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
        "crop_mode": mode,
    }
