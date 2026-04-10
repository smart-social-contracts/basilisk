"""
Basilisk OS — Backward-compatibility re-export layer.

This module re-exports everything from ``ic_basilisk_os`` so that
existing code using ``from basilisk.os import ...`` continues to work.

Install the standalone package::

    pip install ic-basilisk-os
"""

try:
    from ic_basilisk_os import *          # noqa: F401,F403
    from ic_basilisk_os import __all__    # noqa: F401
except ImportError:
    pass
