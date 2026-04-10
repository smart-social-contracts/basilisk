"""
Basilisk OS — Backward-compatibility re-export layer.

This module re-exports everything from ``ic_basilisk_toolkit`` so that
existing code using ``from basilisk.os import ...`` continues to work.

Install the standalone package::

    pip install ic-basilisk-toolkit
"""

try:
    from ic_basilisk_toolkit import *          # noqa: F401,F403
    from ic_basilisk_toolkit import __all__    # noqa: F401
except ImportError:
    pass
