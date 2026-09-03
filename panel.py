# -*- coding: utf-8 -*-
"""panel module - split from AI_View_To_Paint.py (auto-generated)."""
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
from ai_view_to_paint.clients import build_image_client
from ai_view_to_paint.config import ALLOWED_MODELS, DEFAULT_ATLAS_BG, DEFAULT_IMAGE_SIZE, DEFAULT_MODEL, DEFAULT_MULTI_PROMPT, DEFAULT_MULTI_REF_PROMPT, DEFAULT_MULTI_TILE_SIZE, DEFAULT_NORMAL_PROMPT, DEFAULT_OUTPUT_DIR, DEFAULT_PROMPT_ONLY_PROMPT, DEFAULT_PROMPT_ONLY_REF_PROMPT, DEFAULT_SINGLE_PROMPT, DEFAULT_SINGLE_REF_PROMPT, DEFAULT_UV_GUIDE_PROMPT, DEFAULT_UV_GUIDE_REF_PROMPT, DEFAULT_UV_GUIDE_TILE_SIZE, ENABLE_HTTP_DEBUG_BODY, LOG_DEBUG, LOG_ERROR, LOG_INFO, LOG_WARN, MODE_MULTI, MODE_PROMPT_ONLY, MODE_SINGLE, MODE_UV_GUIDE, MULTIVIEW_ROT_PRESETS, MULTIVIEW_SET_4, MULTIVIEW_SET_6, PANEL_OBJECT_NAME, PLUGIN_TITLE, PROJECTOR_DEPTH_SCALE, PROJECTOR_GLOBAL_SCALE_MULTIPLIER, PROJECTOR_ROTATION_EULER_OFFSET, PROJECTOR_VIEW_FIT_SCALE, THUMB_GRID_H, THUMB_GRID_W, THUMB_SIZE, UV_EXPORT_PRESET_NAME
from ai_view_to_paint.dialogs import ReferenceImagesDialog, SettingsDialog
from ai_view_to_paint.image_utils import build_multiview_atlas, load_pixmap_safe, normalize_square_contain_with_manifest, sanitize_png_bytes, split_single_result_by_manifest
from ai_view_to_paint.log_utils import _emit_log, log_debug, set_log_level, set_ui_log_sink
from ai_view_to_paint.utils import ensure_dir, get_image_size_safe, load_plugin_settings, merge_plugin_settings, normalize_path_str, now_str_readable, read_json, safe_remove, save_plugin_settings, ui_join_paths, ui_path_text, unique_stamp, write_binary, write_json
from ai_view_to_paint.widgets import PreviewImageLabel, ThumbIconOnlyDelegate, ThumbListWidget

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
        set_ui_log_sink(self.append_ui_log_line)
        self._sync_log_runtime_settings()

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
        if model not in ALLOWED_MODELS:
            model = DEFAULT_MODEL
        self.model_combo.setCurrentText(model)

        self.update_size_combo_state()

    def update_size_combo_state(self):
        model = self.model_combo.currentText().strip().lower()

        self.size_combo.blockSignals(True)
        try:
            for v in ["1K", "2K", "4K"]:
                if self.size_combo.findText(v) < 0:
                    self.size_combo.addItem(v)

            current_size = str(
                self.settings_data.get("default_image_size", DEFAULT_IMAGE_SIZE) or DEFAULT_IMAGE_SIZE
            ).strip().upper()

            if current_size not in ("1K", "2K", "4K"):
                current_size = DEFAULT_IMAGE_SIZE

            if model == "gpt-image-2":
                self.size_combo.setEnabled(False)
                self.size_combo.setCurrentText("1K")

            elif model == "gpt-image-2-vip":
                self.size_combo.setEnabled(True)
                self.size_combo.setCurrentText(current_size if current_size in ("1K", "2K", "4K") else "2K")

            else:
                self.size_combo.setEnabled(True)
                self.size_combo.setCurrentText(current_size)

        finally:
            self.size_combo.blockSignals(False)

    def persist_output_dir_setting(self):
        self.settings_data = merge_plugin_settings(dict(self.settings_data, **{
            "output_dir": self.output_dir_edit.text().strip() or DEFAULT_OUTPUT_DIR
        }))
        save_plugin_settings(self.settings_data)

    def on_settings_clicked(self):
        old_output_dir = normalize_path_str(self.output_dir_edit.text().strip())

        current_settings = dict(self.settings_data)
        current_settings["output_dir"] = self.output_dir_edit.text().strip() or current_settings.get(
            "output_dir", DEFAULT_OUTPUT_DIR
        )
        current_settings["default_model"] = self.model_combo.currentText().strip() or current_settings.get(
            "default_model", DEFAULT_MODEL
        )

        dlg = SettingsDialog(current_settings, self)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        self.settings_data = save_plugin_settings(dlg.get_settings())
        self._sync_log_runtime_settings()
        self.apply_settings_to_ui()
        self.refresh_client_settings()

        new_output_dir = normalize_path_str(self.output_dir_edit.text().strip())
        if old_output_dir != new_output_dir:
            self.clear_preview()
            self.reload_galleries(log_message=False)

        self.log(
            "设置已保存: provider={} api_base={}".format(
                self.settings_data.get("provider", ""),
                self.settings_data.get("api_base", "")
            ),
            tag="SET"
        )
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
            "nano-banana-pro",
            "gpt-image-2",
            "gpt-image-2-vip",
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
        self.prompt_edit.setMinimumHeight(50)
        self.prompt_edit.setMaximumHeight(120)
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
        self.multi_set_combo.setCurrentText("4视角")
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
        self.log_edit.document().setMaximumBlockCount(1000)
        self.log_edit.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.log_edit.customContextMenuRequested.connect(self.on_log_context_menu)

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
        self.model_combo.currentTextChanged.connect(self.on_model_changed)

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
        self.log("已更新参考图: {} 张".format(count), tag="UI")

        self.refresh_prompt_by_mode_and_refs(force=False)

    def build_submit_image_paths(self, capture_path=None):
        paths = []

        if capture_path:
            paths.append(capture_path)

        paths.extend(self.get_valid_reference_image_paths())
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

    def log(self, text, level=LOG_INFO, tag="UI"):
        _emit_log(level, tag, text)

    def _sync_log_runtime_settings(self):
        debug_enabled = bool(self.settings_data.get("debug_logging", False))
        set_log_level(LOG_DEBUG if debug_enabled else LOG_INFO)

        config.ENABLE_HTTP_DEBUG_BODY = bool(self.settings_data.get("http_debug_body", False))

    def append_ui_log_line(self, text):
        scrollbar = self.log_edit.verticalScrollBar()
        should_stick_bottom = True

        if scrollbar is not None:
            should_stick_bottom = (scrollbar.value() >= scrollbar.maximum() - 4)

        self.log_edit.appendPlainText(str(text))

        if should_stick_bottom and scrollbar is not None:
            scrollbar.setValue(scrollbar.maximum())

    def _normalize_progress_log_key(self, text):
        s = str(text or "").strip()
        low = s.lower()

        if "任务已提交" in s:
            return "submitted"

        if "结果已完成" in s:
            return "download"

        if "网络波动" in s or "重试" in s:
            return s

        if "任务中..." in s:
            status = "unknown"
            progress_bucket = None

            if "status=" in low:
                try:
                    part = low.split("status=", 1)[1]
                    status = part.split()[0].split(",")[0].strip()
                except Exception:
                    pass

            if "progress=" in low:
                try:
                    pstr = low.split("progress=", 1)[1]
                    pnum = ""
                    for ch in pstr:
                        if ch.isdigit():
                            pnum += ch
                        else:
                            break
                    if pnum:
                        p = int(pnum)
                        progress_bucket = min(100, (p // 25) * 25)
                except Exception:
                    progress_bucket = None

            return "poll:{}:{}".format(status, progress_bucket)

        return s

    def set_status(self, text, write_log=False):
        self.status_label.setText(text)
        if write_log:
            self.log(text)
        QtWidgets.QApplication.processEvents()

    def set_status_and_log(self, text, level=LOG_INFO, tag="UI"):
        self.status_label.setText(text)
        self.log(text, level=level, tag=tag)
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

    def tap_key(self, key, wait_ms=180, prefer_viewport=True):
        main_window = substance_painter.ui.get_main_window()
        if main_window is None:
            return False

        try:
            main_window.raise_()
            main_window.activateWindow()
            QtWidgets.QApplication.processEvents()

            target = self.find_viewport_widget() if prefer_viewport else None
            if target is None:
                target = main_window

            try:
                target.setFocus(QtCore.Qt.FocusReason.ActiveWindowFocusReason)
            except Exception:
                pass

            QtWidgets.QApplication.processEvents()
            QtCore.QThread.msleep(40)

            press_event = QtGui.QKeyEvent(
                QtCore.QEvent.Type.KeyPress,
                key,
                QtCore.Qt.KeyboardModifier.NoModifier
            )
            release_event = QtGui.QKeyEvent(
                QtCore.QEvent.Type.KeyRelease,
                key,
                QtCore.Qt.KeyboardModifier.NoModifier
            )

            ok = False

            try:
                QtWidgets.QApplication.sendEvent(target, press_event)
                QtWidgets.QApplication.processEvents()
                QtWidgets.QApplication.sendEvent(target, release_event)
                QtWidgets.QApplication.processEvents()
                ok = True
            except Exception:
                ok = False

            if target is not main_window:
                try:
                    press_event2 = QtGui.QKeyEvent(
                        QtCore.QEvent.Type.KeyPress,
                        key,
                        QtCore.Qt.KeyboardModifier.NoModifier
                    )
                    release_event2 = QtGui.QKeyEvent(
                        QtCore.QEvent.Type.KeyRelease,
                        key,
                        QtCore.Qt.KeyboardModifier.NoModifier
                    )
                    QtWidgets.QApplication.sendEvent(main_window, press_event2)
                    QtWidgets.QApplication.processEvents()
                    QtWidgets.QApplication.sendEvent(main_window, release_event2)
                    QtWidgets.QApplication.processEvents()
                    ok = True
                except Exception:
                    pass

            QtCore.QThread.msleep(max(0, int(wait_ms)))
            self._flush_viewport_frames(frame_count=4, frame_sleep_ms=33)
            return ok

        except Exception as e:
            self.log("模拟按键失败: key={} err={}".format(int(key), e))
            return False

    def tap_f2(self, wait_ms=120):
        return self.tap_key(QtCore.Qt.Key.Key_F2, wait_ms=wait_ms, prefer_viewport=False)

    def tap_f(self, wait_ms=220):
        return self.tap_key(QtCore.Qt.Key.Key_F, wait_ms=wait_ms, prefer_viewport=True)

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

    def _make_camera_state_from_view(self, view_name, ortho=True, fit_scale=1.0):
        if view_name not in MULTIVIEW_ROT_PRESETS:
            raise RuntimeError("未知视角: {}".format(view_name))

        base_state = self.get_camera_state_safe() or {}

        position = list(base_state.get("position", [0.0, 0.0, 0.0]))
        focus_distance = float(base_state.get("focus_distance", 1.0) or 1.0)
        focal_length = float(base_state.get("focal_length", 50.0) or 50.0)
        field_of_view = float(base_state.get("field_of_view", 35.0) or 35.0)
        aperture = float(base_state.get("aperture", 0.0) or 0.0)

        orthographic_height = float(base_state.get("orthographic_height", 2.0) or 2.0)
        if orthographic_height <= 1e-6:
            orthographic_height = 2.0

        rotation = list(MULTIVIEW_ROT_PRESETS.get(view_name, [0.0, 0.0, 0.0]))

        self.log(
            "视角={} 使用当前相机基态切换方向 position={} ortho_h={:.4f}".format(
                view_name, position, orthographic_height
            ),
            tag="CAM"
        )

        return {
            "position": position,
            "rotation": rotation,
            "projection_type": "Orthographic" if ortho else str(base_state.get("projection_type", "Perspective")),
            "field_of_view": field_of_view,
            "focal_length": focal_length,
            "focus_distance": focus_distance,
            "aperture": aperture,
            "orthographic_height": orthographic_height,
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
        elif record.get("is_multiview_group"):
            views = record.get("multiview_views") or []
            lines.append("类型: 多视角组（逐视图 {} 张）".format(len(views)))
        elif record.get("is_multiview_group_result"):
            tiles = record.get("multiview_results") or []
            lines.append("类型: 多视角结果（逐视图 {} 张）".format(len(tiles)))
        elif record.get("mode") == MODE_PROMPT_ONLY:
            lines.append("类型: 提示词生成结果")
        elif record.get("type") == "result" and record.get("mode") == MODE_MULTI:
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
                else ("MV" if record.get("is_multiview_group") else "CP")
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
        elif record.get("is_multiview_group"):
            parts.append("类型: 多视角组")
        elif record.get("mode") == MODE_PROMPT_ONLY:
            parts.append("类型: 提示词生成结果")
        else:
            parts.append("类型: {}".format("结果" if record.get("type") == "result" else "截图"))

        if record.get("is_normal_result"):
            parts.append("说明: AI转换生成的法线贴图")
        elif record.get("is_multiview_group"):
            parts.append("说明: 多视角组（逐视图独立生成）")
        elif record.get("mode") == MODE_PROMPT_ONLY:
            parts.append("说明: 提示词生成，可附带参考图")
        elif record.get("type") == "result" and record.get("mode") == MODE_MULTI:
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

        for view in (record.get("multiview_views") or []):
            if isinstance(view, dict):
                remove_file(view.get("capture_path"))

        for tile in (record.get("multiview_results") or []):
            if isinstance(tile, dict):
                tile_result = str(tile.get("result_path", "") or "").strip()
                if tile_result and normalize_path_str(tile_result) != normalize_path_str(record.get("result_path")):
                    remove_file(tile_result)
                remove_file(tile.get("raw_result_path"))

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
            self.log("已删除: {}".format(ui_join_paths(removed)), tag="FILE")
        else:
            self.log("记录已移除，但没有找到可删除的文件", level=LOG_WARN, tag="FILE")

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

        if record.get("camera_state") and not record.get("is_uvguide_input"):
            act_focus = menu.addAction("定位视角")

        supports_normal_convert = (
                list_widget is self.result_list and
                not record.get("is_normal_result") and
                (
                        record.get("is_uv_result") or
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

    def on_log_context_menu(self, pos):
        menu = self.log_edit.createStandardContextMenu()
        menu.addSeparator()

        act_clear = menu.addAction("清空日志")
        act_copy_all = menu.addAction("复制全部")

        action = menu.exec(self.log_edit.mapToGlobal(pos))

        if action == act_clear:
            self.log_edit.clear()
            self.status_label.setText("日志已清空")

        elif action == act_copy_all:
            text = self.log_edit.toPlainText()
            if text:
                QtWidgets.QApplication.clipboard().setText(text)
                self.status_label.setText("日志已复制")

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
        if record.get("is_multiview_group") or record.get("is_uvguide_input"):
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

        if record.get("is_multiview_group_result"):
            tiles = [
                t for t in (record.get("multiview_results") or [])
                if isinstance(t, dict)
                and t.get("result_path")
                and os.path.exists(t.get("result_path"))
            ]
            if not tiles:
                return None
            return {
                "mode": "multiview_tiles",
                "tiles": tiles,
                "record": record
            }

        if record.get("is_uv_result"):
            return {
                "mode": "uv_texture",
                "record": record
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
                    self.log("读取截图记录失败 {}: {}".format(json_path, e), level=LOG_WARN, tag="GALLERY")

            for json_path in result_jsons:
                try:
                    record = read_json(json_path, default=None)
                    if not isinstance(record, dict):
                        continue
                    record["meta_path"] = json_path
                    self.add_result_item(record, select=False, prepend=False, lazy_icon=False)
                except Exception as e:
                    self.log("读取结果记录失败 {}: {}".format(json_path, e), level=LOG_WARN, tag="GALLERY")

            self.refresh_apply_button_from_selection()

            if log_message:
                self.log("图库已刷新", tag="GALLERY")
        except Exception as e:
            self.log("加载缩略图失败: {}".format(e), level=LOG_ERROR, tag="GALLERY")

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

    def capture_multiview_views_group(self):
        if not substance_painter.project.is_open():
            raise RuntimeError("请先打开一个 Painter 工程")

        output_dir = self.current_output_dir(create=True)
        defs = self.current_multiview_defs()
        original_camera = self.get_camera_state_safe()

        stamp = unique_stamp()
        views = []

        try:
            for slot_name, slot_label in defs:
                self.set_status("自动采集视角: {}".format(slot_label))

                self.tap_f2(wait_ms=120)

                state = self._make_camera_state_from_view(slot_name, ortho=True)
                self.apply_camera_state_and_wait(state, timeout_ms=1200)

                self.tap_f(wait_ms=220)

                self._flush_viewport_frames(frame_count=3, frame_sleep_ms=40)
                final_camera_state = self.get_camera_state_safe() or state
                raw_pixmap = self.capture_current_view()

                pixmap, view_manifest = normalize_square_contain_with_manifest(
                    raw_pixmap,
                    DEFAULT_MULTI_TILE_SIZE,
                    bg=DEFAULT_ATLAS_BG
                )

                view_path = os.path.join(output_dir, "mvview_{}_{}.png".format(stamp, slot_name))
                ok = pixmap.save(view_path, "PNG")
                if not ok:
                    raise RuntimeError("视角图保存失败: {}".format(view_path))

                views.append({
                    "slot_name": slot_name,
                    "slot_label": slot_label,
                    "capture_path": view_path,
                    "camera_state": final_camera_state,
                    "single_view_manifest": view_manifest,
                })

        finally:
            if original_camera:
                self.apply_camera_state_and_wait(original_camera, timeout_ms=1000)

        cover_path = views[0]["capture_path"]
        meta_path = os.path.join(output_dir, "capture_{}.json".format(stamp))

        record = {
            "type": "capture",
            "time": now_str_readable(),
            "stamp": stamp,
            "capture_path": cover_path,
            "camera_state": None,
            "meta_path": meta_path,
            "is_multiview_group": True,
            "multiview_views": views,
            "reference_image_paths": list(self.get_valid_reference_image_paths()),
        }
        write_json(meta_path, record)

        self.add_capture_item(record, select=True, prepend=True, lazy_icon=False)
        self.switch_preview_tab(self.capture_page, keep_selection=True)
        self.status_label.setText("多视角截图完成（{} 张）".format(len(views)))
        self.log("多视角截图完成: {} 张（逐视图独立生成模式）".format(len(views)), tag="CAP")
        return record

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

                self.tap_f2(wait_ms=120)

                state = self._make_camera_state_from_view(slot_name, ortho=True)
                self.apply_camera_state_and_wait(state, timeout_ms=1200)

                self.tap_f(wait_ms=220)

                self._flush_viewport_frames(frame_count=3, frame_sleep_ms=40)
                final_camera_state = self.get_camera_state_safe() or state
                pixmap = self.capture_current_view()

                rec = self.save_capture_record(
                    pixmap=pixmap,
                    output_dir=output_dir,
                    camera_state=final_camera_state,
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
            self.log(
                "UV 输入已创建: uv={} atlas={}".format(
                    ui_path_text(record["uv_layout_path"]),
                    ui_path_text(record["multiview_atlas_path"])
                ),
                tag="CAP"
            )
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
                self.log("提示词生成模式无需截图", tag="CAP")
                return

            if mode == MODE_MULTI:
                self.capture_multiview_views_group()
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
            self.log("截图完成: {}".format(ui_path_text(record["capture_path"])), tag="CAP")
            self.status_label.setText("截图完成")

        except Exception as e:
            self.log(traceback.format_exc(), level=LOG_ERROR, tag="TRACE")
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
        self._sync_log_runtime_settings()
        self.client = self.build_client_from_settings(self.settings_data)

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
                self.log("开始转换法线[UV]", tag="NORMAL")

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

            if record.get("is_multiview_group_result"):
                self.log("开始转换法线[多视角]", tag="NORMAL")

                payload = self.build_apply_payload_from_result_record(record)
                if not payload or payload.get("mode") != "multiview_tiles":
                    raise RuntimeError("多视图结果缺少可用映射信息")

                split_tiles = payload.get("tiles") or []
                if not split_tiles:
                    raise RuntimeError("多视角结果中没有可用视角图")

                self.log("多视角投射准备完成: {} 张".format(len(split_tiles)), tag="NORMAL")

                self.set_status("正在创建临时投射组...")
                temp_group = self.create_multiview_projection_group(
                    split_tiles=split_tiles,
                    group_name="AI_NormalBake_Temp_{}".format(time.strftime("%H%M%S"))
                )

                self.set_status("正在导出颜色贴图...")
                temp_export_path, temp_export_dir = self.export_active_basecolor_map(output_dir)
                self.log("BaseColor 导出完成: {}".format(temp_export_path), tag="NORMAL")

                self.set_status("正在清理临时投射组...")
                self.remove_group_safe(temp_group)
                temp_group = None

                self.log("开始 AI 法线生成", tag="NORMAL")

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
                self.log("开始转换法线[单视角]", tag="NORMAL")

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

            self.log(traceback.format_exc(), level=LOG_ERROR, tag="TRACE")
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

    def is_retryable_generate_error(self, msg):
        text = str(msg or "").lower()
        keys = [
            "google gemini timeout",
            "timeout",
            "timed out",
            "gateway timeout",
            "upstream timeout",
            "temporarily unavailable",
            "failure_reason=error",
        ]
        return any(k in text for k in keys)

    def normalize_model_image_size(self, model, image_size):
        model = str(model or "").strip().lower()
        image_size = str(image_size or "").strip().upper()

        if image_size not in ("1K", "2K", "4K"):
            image_size = DEFAULT_IMAGE_SIZE

        if model == "gpt-image-2":
            return "1K"

        if model == "gpt-image-2-vip":
            return image_size

        if model in ("nano-banana-2", "nano-banana-pro"):
            return image_size

        return DEFAULT_IMAGE_SIZE

    def _short_slot_progress_text(self, text):
        text = str(text or "")
        key = "progress="
        idx = text.find(key)
        if idx >= 0:
            tail = text[idx + len(key):]
            num = ""
            for ch in tail:
                if ch.isdigit():
                    num += ch
                elif num:
                    break
            if num:
                return num + "%"
        if "succeeded" in text or "完成" in text:
            return "完成"
        if "下载" in text:
            return "下载中"
        if "提交" in text:
            return "提交中"
        if "重试" in text:
            return "重试中"
        return text[:12]

    def _generate_multiview_group_record(self, views, prompt, model, aspect_ratio, image_size,
                                         output_dir, ctx, progress_cb, cancel_cb):
        ensure_dir(output_dir)
        stamp = unique_stamp()

        ref_paths = [
            p for p in (ctx.get("reference_image_paths") or [])
            if p and os.path.exists(p)
        ]

        labels = [str(v.get("slot_label") or v.get("slot_name") or "view") for v in views]
        progress_map = {}
        progress_lock = threading.Lock()

        def report_slot_progress(label, text):
            with progress_lock:
                progress_map[label] = self._short_slot_progress_text(text)
                snapshot = dict(progress_map)
            parts = ["{}:{}".format(l, snapshot.get(l, "排队")) for l in labels]
            progress_cb("多视角生成中 " + " ".join(parts))

        outcomes = {}
        outcomes_lock = threading.Lock()

        def run_worker(view):
            slot_name = str(view.get("slot_name") or "view")
            slot_label = str(view.get("slot_label") or slot_name)

            def pcb(text):
                report_slot_progress(slot_label, text)

            try:
                submit_paths = [view.get("capture_path")] + ref_paths

                image_bytes = None
                last_error = None
                max_attempts = 2

                for attempt in range(1, max_attempts + 1):
                    try:
                        if attempt > 1:
                            pcb("提交失败，正在重试({}/{})...".format(attempt, max_attempts))

                        if len(submit_paths) > 1:
                            image_bytes = self.client.generate_from_images(
                                image_paths=submit_paths,
                                prompt=prompt,
                                model=model,
                                aspect_ratio=aspect_ratio,
                                image_size=image_size,
                                shut_progress=True,
                                progress_cb=pcb,
                                cancel_cb=cancel_cb
                            )
                        else:
                            image_bytes = self.client.generate_from_image(
                                image_path=submit_paths[0],
                                prompt=prompt,
                                model=model,
                                aspect_ratio=aspect_ratio,
                                image_size=image_size,
                                shut_progress=True,
                                progress_cb=pcb,
                                cancel_cb=cancel_cb
                            )
                        break

                    except Exception as e:
                        last_error = e
                        if cancel_cb and cancel_cb():
                            raise RuntimeError("已取消")
                        if attempt >= max_attempts or not self.is_retryable_generate_error(str(e)):
                            raise
                        pcb("检测到可重试错误: {}".format(e))
                        wait_left = 2.0
                        while wait_left > 0:
                            if cancel_cb and cancel_cb():
                                raise RuntimeError("已取消")
                            step = min(0.2, wait_left)
                            time.sleep(step)
                            wait_left -= step

                if image_bytes is None:
                    raise RuntimeError("生成失败: 未获得图片数据，last_error={}".format(last_error))

                png_bytes = sanitize_png_bytes(image_bytes)
                img = QtGui.QImage.fromData(png_bytes)
                if img is None or img.isNull():
                    raise RuntimeError("结果图不是有效图片")

                final_path = os.path.join(output_dir, "result_{}_{}.png".format(stamp, slot_name))

                view_manifest = view.get("single_view_manifest")
                if isinstance(view_manifest, dict):
                    try:
                        crop_info = split_single_result_by_manifest(
                            result_image_path=None,
                            manifest=view_manifest,
                            output_path=final_path,
                            image=img
                        )
                        final_path = crop_info["result_path"]
                    except Exception as e:
                        # 裁切失败时保留整图，避免该视角结果丢失
                        pcb("结果裁切失败，保留整图: {}".format(e))
                        write_binary(final_path, png_bytes)
                else:
                    write_binary(final_path, png_bytes)

                pcb("已完成")

                outcome = {
                    "slot_name": slot_name,
                    "slot_label": slot_label,
                    "result_path": final_path,
                    "raw_result_path": "",
                    "camera_state": view.get("camera_state"),
                    "source_capture_path": view.get("capture_path"),
                }

            except Exception as e:
                outcome = {
                    "slot_name": slot_name,
                    "slot_label": slot_label,
                    "error": str(e),
                }

            with outcomes_lock:
                outcomes[slot_name] = outcome

        threads = []
        for view in views:
            t = threading.Thread(target=run_worker, args=(view,), daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        succeeded = []
        failed = []
        for view in views:
            slot_name = str(view.get("slot_name") or "view")
            outcome = outcomes.get(slot_name) or {
                "slot_name": slot_name,
                "slot_label": str(view.get("slot_label") or slot_name),
                "error": "未知错误",
            }
            if outcome.get("error"):
                failed.append(outcome)
            else:
                succeeded.append(outcome)

        for f in failed:
            progress_cb("视角生成失败[{}]: {}".format(f.get("slot_label"), f.get("error")))

        if not succeeded:
            raise RuntimeError("多视角生成全部失败（{} 个视角）".format(len(failed)))

        if failed:
            progress_cb("部分视角失败 {}/{}，已保留成功的 {} 张".format(
                len(failed), len(views), len(succeeded)
            ))

        cover_path = succeeded[0]["result_path"]
        meta_path = os.path.join(output_dir, "result_{}.json".format(stamp))

        record = {
            "type": "result",
            "time": now_str_readable(),
            "stamp": stamp,
            "capture_path": str(ctx.get("record_capture_path", "") or ""),
            "result_path": cover_path,
            "prompt": prompt,
            "model": model,
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,
            "camera_state": None,
            "meta_path": meta_path,
            "reference_image_paths": list(ctx.get("reference_image_paths", [])),
            "mode": MODE_MULTI,
            "is_multiview_group_result": True,
            "multiview_results": succeeded,
            "multiview_failed": failed,
        }

        write_json(meta_path, record)
        return record

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
        image_size = self.size_combo.currentText().strip().upper()

        fixed_image_size = self.normalize_model_image_size(model, image_size)
        if fixed_image_size != image_size:
            self.log(
                "检测到模型 {} 不兼容分辨率 {}，已自动调整为 {}".format(
                    model, image_size, fixed_image_size
                ),
                tag="GEN"
            )
            image_size = fixed_image_size

        output_dir = self.current_output_dir(create=True)

        submit_image_paths = list(input_image_paths or [])
        if not submit_image_paths and capture_path:
            submit_image_paths = [capture_path]

        record_capture_path = str(ctx.get("record_capture_path", capture_path or "") or "").strip()
        mode_name = str(ctx.get("mode", "") or "unknown")
        provider = self.settings_data.get("provider", "")

        self.log(
            "开始生成: mode={} provider={} model={} size={} aspect={} images={}".format(
                mode_name, provider, model, image_size, aspect_ratio, len(submit_image_paths)
            ),
            tag="GEN"
        )

        capture_desc = "-"
        if capture_path and os.path.exists(capture_path):
            w, h = get_image_size_safe(capture_path)
            capture_desc = "{}({}x{})".format(os.path.basename(capture_path), w, h)

        ref_descs = []
        seen = set()
        ref_paths = list(ctx.get("reference_image_paths", []))

        for p in ref_paths:
            p = str(p or "").strip()
            if not p or not os.path.exists(p):
                continue

            norm = normalize_path_str(p)
            if norm in seen:
                continue
            seen.add(norm)

            w, h = get_image_size_safe(p)
            ref_descs.append("{}({}x{})".format(os.path.basename(p), w, h))

        if capture_desc != "-" or ref_descs:
            self.log(
                "输入图: capture={} refs={}".format(
                    capture_desc,
                    ", ".join(ref_descs) if ref_descs else "0"
                ),
                tag="GEN"
            )

        def progress_cb(text):
            self.gen_queue.put({
                "type": "progress",
                "text": text
            })

        def cancel_cb():
            return self.gen_cancel_requested

        def thread_main():
            try:
                if ctx.get("multiview_views"):
                    record = self._generate_multiview_group_record(
                        views=ctx.get("multiview_views"),
                        prompt=prompt,
                        model=model,
                        aspect_ratio=aspect_ratio,
                        image_size=image_size,
                        output_dir=output_dir,
                        ctx=ctx,
                        progress_cb=progress_cb,
                        cancel_cb=cancel_cb
                    )
                    self.gen_queue.put({
                        "type": "finished",
                        "record": record
                    })
                    return

                max_attempts = 2
                image_bytes = None
                last_error = None

                for attempt in range(1, max_attempts + 1):
                    try:
                        if attempt > 1:
                            progress_cb("提交失败，正在重试({}/{})...".format(attempt, max_attempts))

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

                        break

                    except Exception as e:
                        last_error = e
                        err_text = str(e)

                        if cancel_cb and cancel_cb():
                            raise RuntimeError("已取消")

                        if attempt >= max_attempts or not self.is_retryable_generate_error(err_text):
                            raise

                        progress_cb("检测到可重试错误: {}".format(err_text))

                        wait_left = 2.0
                        while wait_left > 0:
                            if cancel_cb and cancel_cb():
                                raise RuntimeError("已取消")
                            step = min(0.2, wait_left)
                            time.sleep(step)
                            wait_left -= step

                if image_bytes is None:
                    raise RuntimeError("生成失败: 未获得图片数据，last_error={}".format(last_error))

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

                key = self._normalize_progress_log_key(text)
                if key != self._last_progress_log_text:
                    self.log(text, tag="GEN")
                    self._last_progress_log_text = key

            elif mtype == "error":
                ctx = self.pending_job_context or {}
                self.cleanup_pending_job_temp_files(ctx)
                self.pending_job_context = None
                self._last_progress_log_text = ""

                self.gen_running = False
                self.gen_thread = None
                self.gen_poll_timer.stop()
                self.set_ui_busy(False)
                self.log(msg.get("trace", ""), level=LOG_ERROR, tag="TRACE")
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

        if record.get("is_multiview_group"):
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

            is_multiview_group = bool(selected_record.get("is_multiview_group"))
            if is_multiview_group:
                views = [
                    v for v in (selected_record.get("multiview_views") or [])
                    if isinstance(v, dict)
                    and v.get("capture_path")
                    and os.path.exists(v.get("capture_path"))
                ]
                if not views:
                    raise RuntimeError("多视角组记录中没有可用的视角图，请重新截图")

                ctx = {
                    "mode": MODE_MULTI,
                    "multiview_views": views,
                    "reference_image_paths": list(ref_paths),
                    "record_capture_path": capture_path,
                }

                self.start_background_generate(
                    capture_path=capture_path,
                    input_image_paths=None,
                    camera_state=None,
                    ctx=ctx,
                    prompt_override=effective_prompt
                )
                return

            camera_state = selected_record.get("camera_state")
            if not camera_state:
                raise RuntimeError("单视角截图缺少 camera_state，无法按单视角生成")

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

                    # 裁切成功后不再保留整图原图（裁切失败时才保留）
                    safe_remove(full_result_path)
                    record["result_path"] = crop_info["result_path"]
                    self.last_result_path = record["result_path"]
                    write_json(record["meta_path"], record)
                    result_path = record["result_path"]
                except Exception as e:
                    self.log("单视角结果裁切失败，保留整图结果: {}".format(e), level=LOG_WARN, tag="GEN")

            item = self.add_result_item(record, select=False, prepend=True, lazy_icon=False)

            self.switch_preview_tab(self.result_page, keep_selection=True)

            if item is not None:
                self.result_list.setCurrentItem(item)
                self.preview_record(record)

            self.log("生成完成: {}".format(result_path), tag="GEN")
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
            self.log("已清理临时组", tag="LAYER")
        else:
            self.log("警告：临时组删除失败，请手动检查图层栈", level=LOG_WARN, tag="LAYER")

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

    def apply_multiview_tiles_to_painter(self, split_tiles, split_manifest_path=None):
        group = self.create_multiview_projection_group(
            split_tiles=split_tiles,
            group_name="AI MultiView {}".format(time.strftime("%H:%M:%S"))
        )

        self.status_label.setText("多视角投射层已创建")
        self.log("多视角结果已应用到 Painter", tag="APPLY")
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
        self.log("单视角结果已应用到 Painter", tag="APPLY")

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
        self.log("UV 结果已作为 UV 贴图应用到 Painter", tag="APPLY")

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
        self.log("法线结果已应用到 Painter", tag="APPLY")

    def apply_payload_internal(self, payload):
        if payload.get("mode") == "multiview_tiles":
            tiles = payload.get("tiles") or []
            if not tiles:
                raise RuntimeError("多视角结果中没有可用视角图")

            self.log("多视角逐视图结果映射，共 {} 张".format(len(tiles)), tag="APPLY")
            self.apply_multiview_tiles_to_painter(tiles, "")

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
            self.log(traceback.format_exc(), level=LOG_ERROR, tag="TRACE")
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
            self.log("已打开输出目录: {}".format(output_dir), tag="FILE")
            self.status_label.setText("已打开输出目录")
        except Exception as e:
            self.log(traceback.format_exc(), level=LOG_ERROR, tag="TRACE")
            self.preview_tabs.setCurrentWidget(self.log_page)
            self.set_status("打开目录失败: {}".format(e))

    def on_output_dir_changed(self):
        self.persist_output_dir_setting()
        self.clear_preview()
        self.reload_galleries(log_message=True)

    def on_image_size_changed(self, text):
        value = (text or "").strip().upper()
        if value not in ("1K", "2K", "4K"):
            return

        self.settings_data = merge_plugin_settings(dict(self.settings_data, **{
            "default_image_size": value
        }))
        save_plugin_settings(self.settings_data)

    def on_model_changed(self, text):
        self.update_size_combo_state()

        model = str(text or "").strip()
        if model not in ALLOWED_MODELS:
            model = DEFAULT_MODEL

        self.settings_data = merge_plugin_settings(dict(self.settings_data, **{
            "default_model": model
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
