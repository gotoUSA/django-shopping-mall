"""
Backward compatibility module for PointHistory.

After service layer separation, PointHistory model was moved to shopping.models.point.
This module re-exports PointHistory to maintain backward compatibility with existing code.
"""

from shopping.models.point import PointHistory

__all__ = ["PointHistory"]
