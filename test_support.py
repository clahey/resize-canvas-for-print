"""Shared test doubles for resize-canvas-for-print.py.

Imports the plugin module by file path (its filename isn't a valid Python
identifier). Fakes are plain MagicMocks with just enough return_values set
for the algorithm to run on real-ish data - every other call (including the
ones under test, like image.resize or layer.resize_to_image_size) is
automatically tracked with no extra setup.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

_MODULE_PATH = Path(__file__).parent / "resize-canvas-for-print.py"
_spec = importlib.util.spec_from_file_location("resize_canvas_for_print", _MODULE_PATH)
rcfp = importlib.util.module_from_spec(_spec)
sys.modules["resize_canvas_for_print"] = rcfp
_spec.loader.exec_module(rcfp)


def make_layer(x, y, w, h, visible=True):
    layer = MagicMock()
    layer.get_visible.return_value = visible
    layer.get_offsets.return_value = (True, x, y)
    layer.get_width.return_value = w
    layer.get_height.return_value = h
    return layer


def make_image(w, h, layers):
    image = MagicMock()
    image.get_width.return_value = w
    image.get_height.return_value = h
    image.get_layers.return_value = layers
    return image


def make_config(values):
    """values maps PDB property names (e.g. "print-axis") to their value."""
    config = MagicMock()
    config.get_property.side_effect = lambda name: values[name]
    return config
