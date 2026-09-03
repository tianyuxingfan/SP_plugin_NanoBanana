# -*- coding: utf-8 -*-
"""AI View To Paint - Substance 3D Painter plugin.

这个包本身即是插件入口：Substance Painter 会把 plugins 目录下的
ai_view_to_paint 文件夹作为插件加载，并调用 start_plugin / close_plugin。
"""

from ai_view_to_paint.plugin import start_plugin, close_plugin

__all__ = ["start_plugin", "close_plugin"]
