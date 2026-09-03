# -*- coding: utf-8 -*-
"""widgets module - split from AI_View_To_Paint.py (auto-generated)."""
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
from ai_view_to_paint.config import THUMB_GRID_H, THUMB_GRID_W

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
