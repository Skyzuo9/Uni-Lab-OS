"""Layout Optimizer — Uni-Lab-OS 集成模块。

以单例 LayoutService 对外提供 interpret / optimize / devices 功能。
"""
from .service import LayoutService

__all__ = ["LayoutService"]
