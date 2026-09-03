# -*- coding: utf-8 -*-
"""dialogs module - split from AI_View_To_Paint.py (auto-generated)."""
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
from ai_view_to_paint.config import API_BASE, DEFAULT_MODEL, DEFAULT_OUTPUT_DIR, PROVIDER_GRSAI, PROVIDER_PRESETS, PROVIDER_RUNNINGHUB, RESULT_PATH, RUNNINGHUB_API_BASE, RUNNINGHUB_DEFAULT_SUBMIT_PATH, RUNNINGHUB_RESULT_PATH, RUNNINGHUB_TEXT_PATH, RUNNINGHUB_UPLOAD_BINARY, RUNNINGHUB_UPLOAD_DATA_URI, RUNNINGHUB_UPLOAD_PATH, SUBMIT_PATH
from ai_view_to_paint.utils import merge_plugin_settings, normalize_path_str
from ai_view_to_paint.widgets import QLabelPreviewBox

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

        self.runninghub_text_path_edit = QtWidgets.QLineEdit(
            self.settings_data.get("runninghub_text_path", RUNNINGHUB_TEXT_PATH)
        )
        self.form.addRow("文生图路径", self.runninghub_text_path_edit)

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
        text_path_label = self.form.labelForField(self.runninghub_text_path_edit)
        upload_label = self.form.labelForField(self.runninghub_upload_path_edit)
        upload_mode_label = self.form.labelForField(self.runninghub_upload_mode_combo)

        show_submit_result = is_runninghub
        self.submit_path_edit.setVisible(show_submit_result)
        self.result_path_edit.setVisible(show_submit_result)
        self.runninghub_text_path_edit.setVisible(show_submit_result)

        if submit_label is not None:
            submit_label.setVisible(show_submit_result)
        if result_label is not None:
            result_label.setVisible(show_submit_result)
        if text_path_label is not None:
            text_path_label.setVisible(show_submit_result)

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
            # 仅当输入框为空、或仍显示另一平台（GRSAI）的预设值时才覆盖，
            # 保留用户自定义的路径；避免切换平台后残留 GRSAI 的路径
            current_base = self.api_base_edit.text().strip()
            if not current_base or current_base == API_BASE:
                self.api_base_edit.setText(preset.get("api_base", RUNNINGHUB_API_BASE))

            current_submit = self.submit_path_edit.text().strip()
            if not current_submit or current_submit == SUBMIT_PATH:
                self.submit_path_edit.setText(preset.get("submit_path", RUNNINGHUB_DEFAULT_SUBMIT_PATH))

            current_result = self.result_path_edit.text().strip()
            if not current_result or current_result == RESULT_PATH:
                self.result_path_edit.setText(preset.get("result_path", RUNNINGHUB_RESULT_PATH))

            current_text_path = self.runninghub_text_path_edit.text().strip()
            if not current_text_path or current_text_path == RUNNINGHUB_TEXT_PATH:
                self.runninghub_text_path_edit.setText(preset.get("text_submit_path", RUNNINGHUB_TEXT_PATH))

            current_upload = self.runninghub_upload_path_edit.text().strip()
            if not current_upload or current_upload == RUNNINGHUB_UPLOAD_PATH:
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
            "runninghub_text_path": self.runninghub_text_path_edit.text().strip() if provider == PROVIDER_RUNNINGHUB else preset.get(
                "text_submit_path", RUNNINGHUB_TEXT_PATH),
            "runninghub_upload_path": self.runninghub_upload_path_edit.text().strip() if provider == PROVIDER_RUNNINGHUB else preset.get(
                "upload_path", RUNNINGHUB_UPLOAD_PATH),
            "runninghub_upload_mode": self.runninghub_upload_mode_combo.currentData() if provider == PROVIDER_RUNNINGHUB else preset.get(
                "upload_mode", RUNNINGHUB_UPLOAD_DATA_URI),
            "default_model": self.model_edit.text().strip(),
            "output_dir": self.output_dir_edit.text().strip(),
        })


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
