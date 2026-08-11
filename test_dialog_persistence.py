"""Tests for Dialog & Persistence (RCFP-DIALOG-*).

default_print_size and print_size_from_config are pure computation - the
values PERSIST-004/007 describe defaulting the dialog's fields to - and are
exercised directly. Everything else runs through the full
ResizeCanvasForPrint.run pipeline, since it's genuinely reachable that way:
config is a plain property bag, and run_resize_canvas_for_print's Gimp API
calls are the closest thing this side-effecting code has to an observable
output.

show_dialog itself is intentionally not covered here - it constructs real
GTK widgets and blocks on a real event loop, and there's no lightweight GTK
test framework available to drive that without a real (or headless)
display. PERSIST-002/003/009/011, APPLY-005, and UNIT-001/002/003/004/006,
whose logic lives inside show_dialog, stay manually/live-verified for the
same reason - as do PERSIST-004/006/007's unit-conversion-for-display
clauses specifically (their underlying fit/default computation is still
covered directly, per above). UNIT-007's bounds-scaling formula is covered
directly via size_field_bounds; only its wiring into the live spin buttons
on unit change is manually/live-verified.

PERSIST-001/008 (declaring PDB arguments and their defaults in
do_create_procedure) are a real, closeable gap left untested by choice -
that function is never exercised here.
"""

from unittest.mock import MagicMock, patch

import pytest

from test_support import make_config, make_image, make_layer, rcfp


# --- default_print_size / print_size_from_config (RCFP-DIALOG-PERSIST-004, 007) --

# @spec RCFP-DIALOG-PERSIST-007
def test_default_print_size_landscape_crop_matches_preset_aspect():
    w, h = rcfp.default_print_size(3000, 2000)
    assert (w, h) == pytest.approx((6.0, 4.0))


# @spec RCFP-DIALOG-PERSIST-007
def test_default_print_size_square_crop_uses_short_edge():
    w, h = rcfp.default_print_size(1000, 1000)
    assert (w, h) == pytest.approx((4.0, 4.0))


# @spec RCFP-DIALOG-PERSIST-007
def test_print_size_from_config_no_axis_uses_default_fit():
    image = make_image(3000, 2000, [make_layer(0, 0, 3000, 2000)])
    w, h = rcfp.print_size_from_config(image, "", 6.0)
    assert (w, h) == pytest.approx((6.0, 4.0))


# @spec RCFP-DIALOG-PERSIST-004
def test_print_size_from_config_width_axis_clamped_to_fit():
    image = make_image(3000, 2000, [make_layer(0, 0, 3000, 2000)])
    w, h = rcfp.print_size_from_config(image, "width", 20.0)
    assert (w, h) == pytest.approx((6.0, 4.0))


# @spec RCFP-DIALOG-PERSIST-004
def test_print_size_from_config_width_axis_below_fit_kept_and_height_rederived():
    image = make_image(3000, 2000, [make_layer(0, 0, 3000, 2000)])
    w, h = rcfp.print_size_from_config(image, "width", 3.0)
    assert (w, h) == pytest.approx((3.0, 2.0))


# @spec RCFP-DIALOG-PERSIST-004
def test_print_size_from_config_height_axis_below_fit_kept_and_width_rederived():
    image = make_image(3000, 2000, [make_layer(0, 0, 3000, 2000)])
    w, h = rcfp.print_size_from_config(image, "height", 2.0)
    assert (w, h) == pytest.approx((3.0, 2.0))


# --- unit conversion (RCFP-DIALOG-UNIT-005) ---------------------------------

@pytest.mark.parametrize("unit,per_inch", [
    (rcfp.Gimp.Unit.inch(), 1.0),
    (rcfp.Gimp.Unit.mm(), 25.4),
    (rcfp.Gimp.Unit.point(), 72.0),
    (rcfp.Gimp.Unit.pica(), 6.0),
])
# @spec RCFP-DIALOG-UNIT-005
def test_to_inches_converts_one_unit_of_each_kind_to_one_inch(unit, per_inch):
    assert rcfp.to_inches(per_inch, unit) == pytest.approx(1.0)


# @spec RCFP-DIALOG-UNIT-005
def test_from_inches_undoes_to_inches():
    for unit in (rcfp.Gimp.Unit.inch(), rcfp.Gimp.Unit.mm(), rcfp.Gimp.Unit.point(), rcfp.Gimp.Unit.pica()):
        assert rcfp.from_inches(rcfp.to_inches(5.0, unit), unit) == pytest.approx(5.0)


# @spec RCFP-DIALOG-UNIT-007
def test_print_size_field_bounds_scale_with_unit():
    inch = rcfp.Gimp.Unit.inch()
    point = rcfp.Gimp.Unit.point()
    lower_in, upper_in = rcfp.size_field_bounds(inch)
    lower_pt, upper_pt = rcfp.size_field_bounds(point)
    assert (lower_in, upper_in) == pytest.approx(
        (rcfp.SIZE_FIELD_LOWER_IN, rcfp.SIZE_FIELD_UPPER_IN))
    assert (lower_pt, upper_pt) == pytest.approx((lower_in * 72.0, upper_in * 72.0))
    # 3 inches must fit comfortably within the pt-unit upper bound.
    assert rcfp.to_inches(upper_pt, point) == pytest.approx(upper_in)
    assert upper_pt > rcfp.from_inches(3.0, point)


# @spec RCFP-DIALOG-UNIT-005, RCFP-DIALOG-PERSIST-010
def test_non_interactive_run_converts_persisted_units_to_inches(run_plugin):
    # Landscape 2:1 crop. print-value is 1 inch stored as 72pt;
    # custom-width/height are 1in/2in stored as 25.4mm/50.8mm. If the
    # stored numbers were used as-is (without unit conversion) the
    # resulting resolution and canvas size would be wildly different.
    crop_w, crop_h = 2000, 1000
    image = make_image(crop_w, crop_h, [make_layer(0, 0, crop_w, crop_h)])
    config = make_config({
        "print-axis": "width",
        "print-value": 72.0,
        "print-unit": rcfp.Gimp.Unit.point(),
        "preset-idx": len(rcfp.PRESETS) - 1,  # Custom
        "custom-width": 25.4,
        "custom-height": 50.8,
        "custom-unit": rcfp.Gimp.Unit.mm(),
    })

    run_plugin(image, config, rcfp.Gimp.RunMode.WITH_LAST_VALS)

    image.set_resolution.assert_called_once()
    xres, yres = image.set_resolution.call_args.args
    assert (xres, yres) == pytest.approx((2000.0, 2000.0))

    image.resize.assert_called_once()
    target_w, target_h, offx, offy = image.resize.call_args.args
    assert (target_w, target_h) == (2000, 4000)
    assert (offx, offy) == (0, 1500)


# --- apply (RCFP-DIALOG-APPLY-001, 003, 004) -------------------------------

@pytest.fixture
def default_config():
    return make_config({
        "print-axis": "",
        "print-value": 6.0,
        "print-unit": rcfp.Gimp.Unit.inch(),
        "preset-idx": len(rcfp.PRESETS) - 1,  # Custom - isolates apply from orientation
        "custom-width": 4.0,
        "custom-height": 6.0,
        "custom-unit": rcfp.Gimp.Unit.inch(),
    })


# @spec RCFP-DIALOG-APPLY-001, RCFP-DIALOG-APPLY-003, RCFP-DIALOG-APPLY-004
def test_apply_sets_resolution_and_resizes_layers_white(run_plugin, default_config):
    image = make_image(828, 829, [
        make_layer(-1702, -2062, 4096, 6144),
        make_layer(-1702, -2062, 4096, 6144),
    ])

    with patch.object(rcfp, "print_size_from_config", return_value=(1.0, 1.0012077)):
        run_plugin(image, default_config, rcfp.Gimp.RunMode.WITH_LAST_VALS)

    image.set_resolution.assert_called_once()
    xres, yres = image.set_resolution.call_args.args
    assert xres == pytest.approx(828.0)
    assert yres == pytest.approx(828.0)

    image.resize.assert_called_once()
    target_w, target_h, _offx, _offy = image.resize.call_args.args
    assert (target_w, target_h) == (3312, 4968)

    for layer in image.get_layers.return_value:
        layer.resize_to_image_size.assert_called_once()
    rcfp.Gimp.context_set_background.assert_called_once_with(rcfp.Gegl.Color.new.return_value)
    rcfp.Gegl.Color.new.assert_called_once_with("white")
    rcfp.Gimp.displays_flush.assert_called_once()


# --- PERSIST-005: non-interactive run modes skip the dialog ----------------

@pytest.mark.parametrize("run_mode_name", ["WITH_LAST_VALS", "NONINTERACTIVE"])
# @spec RCFP-DIALOG-PERSIST-005
def test_non_interactive_modes_skip_dialog_and_apply_config(run_plugin, default_config, run_mode_name):
    image = make_image(828, 829, [make_layer(-1702, -2062, 4096, 6144)])

    with patch.object(rcfp, "show_dialog",
                       side_effect=AssertionError(f"dialog should not show for {run_mode_name}")):
        run_plugin(image, default_config, getattr(rcfp.Gimp.RunMode, run_mode_name))

    image.resize.assert_called_once()


# --- run(): interactive wiring around show_dialog ---------------------------
# show_dialog is treated as a black box here (mocked entirely), so these
# test run()'s own branching, not any Dialog & Persistence spec directly.

def test_run_interactive_shows_dialog_and_applies_its_result(run_plugin, mock_gimp):
    image = MagicMock()
    config = MagicMock()

    with patch.object(rcfp, "show_dialog", return_value=(4.0, 6.0, 4.0, 6.0)) as mock_show_dialog, \
            patch.object(rcfp, "run_resize_canvas_for_print") as mock_apply:
        procedure = run_plugin(image, config, mock_gimp.RunMode.INTERACTIVE)

    mock_show_dialog.assert_called_once_with(image, config)
    mock_apply.assert_called_once_with(image, 4.0, 6.0, 4.0, 6.0)
    status = procedure.new_return_values.call_args.args[0]
    assert status == mock_gimp.PDBStatusType.SUCCESS


def test_run_interactive_cancel_skips_apply(run_plugin, mock_gimp):
    image = MagicMock()
    config = MagicMock()

    with patch.object(rcfp, "show_dialog", return_value=None), \
            patch.object(rcfp, "run_resize_canvas_for_print") as mock_apply:
        procedure = run_plugin(image, config, mock_gimp.RunMode.INTERACTIVE)

    mock_apply.assert_not_called()
    status = procedure.new_return_values.call_args.args[0]
    assert status == mock_gimp.PDBStatusType.CANCEL
