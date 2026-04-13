"""Layout Optimizer — Uni-Lab-OS 集成模块。

以同进程模块方式提供实验室布局自动优化功能。
Mock 模式无 ROS 依赖；MoveIt 模式需要 ROS2 + MoveIt2。
"""

from .models import Constraint, Device, Lab, Opening, Placement
from .optimizer import optimize

__all__ = ["Device", "Lab", "Opening", "Placement", "Constraint", "optimize"]
