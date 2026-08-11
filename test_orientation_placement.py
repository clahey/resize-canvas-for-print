"""Tests for Orientation & Placement (RCFP-ORIENT-*).

get_visible_layers_bbox is exercised directly - it's a helper with no
specified behavior of its own. Everything else runs through the full
ResizeCanvasForPrint.run pipeline (Gimp/GLib/Gegl mocked, real geometry on
MagicMock image/layers), asserting on the resulting image.resize(...) call -
target_w/target_h reveal which orientation was chosen, offx/offy reveal the
placement decision. print_size_from_config is patched to a fixed print
size in these tests, since its own clamping (persisted-value-vs-fit) is
Dialog & Persistence behavior, tested separately, and would otherwise make
some of these scenarios unreachable (see dialog-persistence-design.md).
"""

from unittest.mock import patch

from test_support import make_config, make_image, make_layer, rcfp

NON_CUSTOM_PRESET_IDX = 0


def default_config(preset_idx=NON_CUSTOM_PRESET_IDX, custom_w=4.0, custom_h=6.0):
    return make_config({
        "print-axis": "",
        "print-value": 6.0,
        "print-unit": rcfp.Gimp.Unit.inch(),
        "preset-idx": preset_idx,
        "custom-width": custom_w,
        "custom-height": custom_h,
        "custom-unit": rcfp.Gimp.Unit.inch(),
    })


def resize_pipeline(run_plugin, image, print_w_in, print_h_in, config=None):
    with patch.object(rcfp, "print_size_from_config", return_value=(print_w_in, print_h_in)):
        run_plugin(image, config or default_config(), rcfp.Gimp.RunMode.WITH_LAST_VALS)
    return image


# --- get_visible_layers_bbox --------------------------------------------

def test_bbox_single_layer():
    image = make_image(100, 100, [make_layer(0, 0, 100, 100)])
    assert rcfp.get_visible_layers_bbox(image) == (0, 0, 100, 100)


def test_bbox_ignores_hidden_layers_when_visible_exist():
    hidden = make_layer(-1000, -1000, 1, 1, visible=False)
    visible = make_layer(0, 0, 50, 50, visible=True)
    image = make_image(50, 50, [hidden, visible])
    assert rcfp.get_visible_layers_bbox(image) == (0, 0, 50, 50)


def test_bbox_falls_back_to_all_layers_when_none_visible():
    hidden = make_layer(10, 20, 30, 40, visible=False)
    image = make_image(100, 100, [hidden])
    assert rcfp.get_visible_layers_bbox(image) == (10, 20, 40, 60)


def test_bbox_unions_multiple_visible_layers():
    a = make_layer(0, 0, 10, 10)
    b = make_layer(5, 5, 10, 10)
    image = make_image(15, 15, [a, b])
    assert rcfp.get_visible_layers_bbox(image) == (0, 0, 15, 15)


# --- crop-loss gate (RCFP-ORIENT-002, 003, 004, 005) ---------------------

# @spec RCFP-ORIENT-002, RCFP-ORIENT-003, RCFP-ORIENT-004, RCFP-ORIENT-005
def test_crop_forced_in_one_orientation_only_picks_the_other(run_plugin):
    # Landscape crop; print size chosen to exactly match the preset's
    # landscape paper (6x4), so only portrait (4x6) paper would crop it.
    crop_w, crop_h = 1800, 1200
    image = make_image(crop_w, crop_h, [make_layer(0, 0, crop_w, crop_h)])
    resize_pipeline(run_plugin, image, print_w_in=6.0, print_h_in=4.0)

    image.resize.assert_called_once()
    target_w, target_h, offx, offy = image.resize.call_args.args
    assert (target_w, target_h) == (1800, 1200)
    assert (offx, offy) == (0, 0)


# @spec RCFP-ORIENT-002, RCFP-ORIENT-003, RCFP-ORIENT-004, RCFP-ORIENT-005
def test_crop_forced_in_both_orientations_picks_the_lesser(run_plugin):
    # Portrait crop; print size (4.1x6.1) is slightly larger than the 4x6
    # paper in both orientations, but landscape (6x4 paper vs a 6.1in-tall
    # print) crops far more than portrait (4x6 paper vs a 4.1x6.1 print).
    crop_w, crop_h = 1200, 1800
    image = make_image(crop_w, crop_h, [make_layer(0, 0, crop_w, crop_h)])
    resize_pipeline(run_plugin, image, print_w_in=4.1, print_h_in=6.1)

    image.resize.assert_called_once()
    target_w, target_h, offx, offy = image.resize.call_args.args
    assert target_w < target_h  # portrait
    assert (target_w, target_h) == (1171, 1770)


# --- tie-break (RCFP-ORIENT-006, 007) -------------------------------------

# @spec RCFP-ORIENT-006
def test_tiebreak_near_square_crop_tall_layer_picks_portrait(run_plugin):
    # Real regression case: crop just 1px off square, bbox from a much
    # taller source layer. Portrait wins on the weighted tie-break.
    image = make_image(828, 829, [make_layer(-1702, -2062, 4096, 6144)])
    resize_pipeline(run_plugin, image, print_w_in=1.0, print_h_in=1.0012077)

    target_w, target_h, _offx, _offy = image.resize.call_args.args
    assert target_w < target_h  # portrait


# @spec RCFP-ORIENT-006
def test_tiebreak_sliver_crop_matching_paper_picks_landscape(run_plugin):
    # Real regression case: a wide sliver crop from a much taller layer,
    # print size chosen to exactly match the crop's own shape.
    image = make_image(100, 25, [make_layer(0, 0, 100, 1000)])
    resize_pipeline(run_plugin, image, print_w_in=4.0, print_h_in=1.0)

    target_w, target_h, _offx, _offy = image.resize.call_args.args
    assert target_w > target_h  # landscape


# @spec RCFP-ORIENT-006
def test_tiebreak_sliver_crop_less_extreme_bbox_still_picks_landscape(run_plugin):
    image = make_image(100, 25, [make_layer(0, 0, 100, 750)])
    resize_pipeline(run_plugin, image, print_w_in=4.0, print_h_in=1.0)

    target_w, target_h, _offx, _offy = image.resize.call_args.args
    assert target_w > target_h  # landscape


# @spec RCFP-ORIENT-007
def test_tiebreak_all_tied_defaults_to_landscape(run_plugin):
    # Square crop, generous square bbox on all sides: gate and weighted
    # cost both tie exactly, so the final tie-break (landscape) applies.
    image = make_image(100, 100, [make_layer(-1000, -1000, 4000, 4000)])
    resize_pipeline(run_plugin, image, print_w_in=4.0, print_h_in=4.0)

    target_w, target_h, _offx, _offy = image.resize.call_args.args
    assert target_w > target_h  # landscape


# --- placement (RCFP-ORIENT-008, 009) -------------------------------------

# @spec RCFP-ORIENT-008
def test_placement_clamps_into_bbox_when_canvas_fits(run_plugin):
    # bbox has plenty of spare layer data on the width axis: the canvas
    # should land fully inside it rather than spilling past the edge.
    crop_w, crop_h = 100, 150
    image = make_image(crop_w, crop_h, [make_layer(-500, 0, 1000, crop_h)])
    resize_pipeline(run_plugin, image, print_w_in=4.0, print_h_in=6.0)

    _target_w, _target_h, offx, offy = image.resize.call_args.args
    assert offx == 0
    assert offy == 0


# @spec RCFP-ORIENT-009
def test_placement_centers_on_bbox_when_canvas_bigger_than_bbox(run_plugin):
    # bbox is smaller than the resulting canvas on the width axis: no
    # amount of clamping avoids white space, so it centers on the bbox.
    crop_w, crop_h = 100, 150
    image = make_image(crop_w, crop_h, [make_layer(25, 0, 50, crop_h)])
    resize_pipeline(run_plugin, image, print_w_in=4.0, print_h_in=6.0)

    _target_w, _target_h, offx, offy = image.resize.call_args.args
    assert offx == 0


# --- get_canvas_size: Custom mode (RCFP-ORIENT-001) -----------------------
# Also covers RCFP-DIALOG-APPLY-002's Custom-mode extent sourcing.

# @spec RCFP-ORIENT-001, RCFP-DIALOG-APPLY-002
def test_custom_mode_uses_typed_values_directly_no_orientation_decision(run_plugin):
    image = make_image(828, 829, [make_layer(-1702, -2062, 4096, 6144)])
    custom_idx = len(rcfp.PRESETS) - 1
    assert rcfp.PRESETS[custom_idx][0] == "Custom"
    config = default_config(preset_idx=custom_idx, custom_w=7.5, custom_h=3.25)
    resize_pipeline(run_plugin, image, print_w_in=1.0, print_h_in=1.0012077, config=config)

    target_w, target_h, _offx, _offy = image.resize.call_args.args
    assert (target_w, target_h) == (6210, 2691)
