#!/usr/bin/env python3

"""GIMP 3.0 plug-in: set print resolution and resize the canvas to a
standard photo size, centering the current crop and pulling in extra
layer data (from non-destructive crops) before falling back to white
padding.
"""

import sys

import gi

gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
gi.require_version("Gegl", "0.4")
from gi.repository import Gegl, Gimp, GimpUi, GLib, GObject, Gtk  # noqa: E402

PROC_NAME = "python-fu-resize-canvas-for-print"

# (label, short_edge_in, long_edge_in) - values of None marks "Custom".
# Orientation is not part of the preset; it's decided separately (see
# best_orientation).
PRESETS = [
    ("4 x 6 in", 4.0, 6.0),
    ("5 x 7 in", 5.0, 7.0),
    ("8 x 10 in", 8.0, 10.0),
    ("Custom", None, None),
]

# GIMP's built-in physical length units (pixels and percent excluded - see
# RCFP-DIALOG-UNIT-006). GIMP has no built-in centimeter unit.
UNITS_PER_INCH = {
    "in": 1.0,
    "mm": 25.4,
    "pt": 72.0,
    "pica": 6.0,
}

# Print-size and Custom-canvas-size field bounds, fixed in inches and
# converted to whichever unit is selected - a flat 0.1-100 range in every
# unit would let pt/pica max out below a single inch. See RCFP-DIALOG-UNIT-007.
SIZE_FIELD_LOWER_IN = 0.1
SIZE_FIELD_UPPER_IN = 100.0


def to_inches(value, unit):
    return value / UNITS_PER_INCH[unit]


def from_inches(value_in, unit):
    return value_in * UNITS_PER_INCH[unit]


def size_field_bounds(unit):
    """(lower, upper) for a print-size or Custom-canvas-size field, in
    `unit` - fixed in inches (SIZE_FIELD_LOWER_IN/SIZE_FIELD_UPPER_IN) and
    converted, so the usable range doesn't shrink in a smaller unit
    (RCFP-DIALOG-UNIT-007)."""
    return from_inches(SIZE_FIELD_LOWER_IN, unit), from_inches(SIZE_FIELD_UPPER_IN, unit)


def get_visible_layers_bbox(image):
    """Union bounding box (in image/canvas coordinates) of all visible
    layers. Falls back to all layers if none are visible."""
    layers = [l for l in image.get_layers() if l.get_visible()]
    if not layers:
        layers = image.get_layers()

    boxes = []
    for layer in layers:
        _success, ox, oy = layer.get_offsets()
        w = layer.get_width()
        h = layer.get_height()
        boxes.append({"x0": ox, "y0": oy, "x1": ox + w, "y1": oy + h})

    return (
        min(b["x0"] for b in boxes),
        min(b["y0"] for b in boxes),
        max(b["x1"] for b in boxes),
        max(b["y1"] for b in boxes),
    )


def placement_for_axis(crop_extent, bbox_lo, bbox_hi, target_extent):
    """Where should the new canvas's origin land (in current-canvas
    coordinates) on one axis?

    If the target canvas is no bigger than the available layer data on
    this axis, it can always be placed with zero white space: clamp the
    crop-centered position into the range where it fits entirely inside
    the bbox. Otherwise the target is simply bigger than what we have,
    so white space is unavoidable on this axis - center on the bbox
    instead of the crop so the padding is even.
    """
    ideal = (crop_extent - target_extent) / 2.0
    layer_extent = bbox_hi - bbox_lo
    if target_extent <= layer_extent:
        return min(max(ideal, bbox_lo), bbox_hi - target_extent)
    return bbox_lo + (layer_extent - target_extent) / 2.0


def default_print_size(crop_w, crop_h):
    """Default print size for the primary preset (PRESETS[0], e.g. 4x6):
    the largest size that fits inside the canvas without cropping,
    aligning the canvas's short edge with the crop's short dimension and
    its long edge with the crop's long dimension. That pairing always
    fits at least as well as the swapped one, so there's no need to try
    both and compare.
    """
    short_in, long_in = PRESETS[0][1:]  # 4.0, 6.0

    short_dim = min(crop_w, crop_h)
    long_dim = max(crop_w, crop_h)
    scale = min(short_in / short_dim, long_in / long_dim)

    return crop_w * scale, crop_h * scale


def print_size_from_config(image, axis, value):
    """Default print size: whichever of width/height the user explicitly
    set last time (only one axis is remembered - the crop's aspect ratio
    will rarely match exactly between sessions, so re-deriving a stored
    "other axis" value would usually be wrong). The remembered value is
    clamped to the "fits without cropping" size for the *current* crop,
    since an old value may not suit a differently shaped crop; the other
    axis is always re-derived fresh from the current crop's aspect
    ratio, never remembered directly. `axis` is "width", "height", or ""
    (never set - e.g. the very first run).
    """
    crop_w = image.get_width()
    crop_h = image.get_height()
    fit_w, fit_h = default_print_size(crop_w, crop_h)
    aspect = crop_w / crop_h
    if axis == "width":
        w = min(value, fit_w)
        return w, w / aspect
    if axis == "height":
        h = min(value, fit_h)
        return h * aspect, h
    return fit_w, fit_h


def _clamped_ratio_cost(bigger, smaller):
    """(bigger-smaller)^2 / (bigger*smaller) if bigger > smaller, else 0.

    Scale-invariant: comparable across wildly different pixel scales,
    unlike a raw squared-pixel difference.
    """
    if bigger <= smaller:
        return 0.0
    diff = bigger - smaller
    return diff * diff / (bigger * smaller)


def best_orientation(image, print_w_in, print_h_in, w_in, h_in):
    """Given a canvas size as an unordered (w_in, h_in) pair, return
    whichever orientation - (w_in, h_in) or (h_in, w_in) - is the better
    fit.

    Primary (decisive) criterion: pixels cropped out of the print itself
    (paper size smaller than the print size, i.e. the crop's own pixel
    dimensions, on some axis). If the two orientations differ here at
    all, whichever crops less wins outright - nothing else is considered.

    Otherwise (the common case: the bbox has enough spare layer data to
    cover either orientation without cropping the print), break the tie
    by a weighted sum of three comparable, scale-invariant costs, each
    measured per axis:
      - margin: paper size bigger than the print size (extending past
        the crop using bbox data) - weight 3.
      - content_loss: bbox bigger than the paper size (real photo data
        available but left out of the final canvas) - weight 1.5.
      - white_space: paper size bigger than the bbox (no real data left
        to draw on - genuine padding) - weight 1.
    Lower total wins; landscape wins an exact tie.
    """
    crop_w = image.get_width()
    crop_h = image.get_height()
    xres = crop_w / print_w_in
    yres = crop_h / print_h_in
    bx0, by0, bx1, by1 = get_visible_layers_bbox(image)
    bbox_w = bx1 - bx0
    bbox_h = by1 - by0

    def crop_loss(w, h):
        target_w = w * xres
        target_h = h * yres
        dw = max(0.0, crop_w - target_w)
        dh = max(0.0, crop_h - target_h)
        return dw * dw + dh * dh

    def weighted_cost(w, h):
        target_w = w * xres
        target_h = h * yres
        margin = (_clamped_ratio_cost(target_w, crop_w)
                  + _clamped_ratio_cost(target_h, crop_h))
        content_loss = (_clamped_ratio_cost(bbox_w, target_w)
                         + _clamped_ratio_cost(bbox_h, target_h))
        white_space = (_clamped_ratio_cost(target_w, bbox_w)
                        + _clamped_ratio_cost(target_h, bbox_h))
        return 3.0 * margin + 1.5 * content_loss + 1.0 * white_space

    portrait_crop_loss = crop_loss(w_in, h_in)
    landscape_crop_loss = crop_loss(h_in, w_in)

    if portrait_crop_loss != landscape_crop_loss:
        return (h_in, w_in) if landscape_crop_loss < portrait_crop_loss else (w_in, h_in)

    portrait_cost = weighted_cost(w_in, h_in)
    landscape_cost = weighted_cost(h_in, w_in)
    return (h_in, w_in) if landscape_cost <= portrait_cost else (w_in, h_in)


def get_canvas_size(image, preset_idx, print_w_in, print_h_in,
                     custom_w_in, custom_h_in):
    """The canvas size to actually use, decided once (at OK time): the
    user's own values in Custom mode, otherwise the better-fitting
    orientation of the selected preset at the final print size."""
    _label, w, h = PRESETS[preset_idx]
    if w is None:  # Custom
        return custom_w_in, custom_h_in
    return best_orientation(image, print_w_in, print_h_in, w, h)


def run_resize_canvas_for_print(image, print_w_in, print_h_in, canvas_w_in, canvas_h_in):
    crop_w = image.get_width()
    crop_h = image.get_height()

    bx0, by0, bx1, by1 = get_visible_layers_bbox(image)

    xres = crop_w / print_w_in
    yres = crop_h / print_h_in

    image.undo_group_start()
    try:
        image.set_resolution(xres, yres)

        target_w = int(round(canvas_w_in * xres))
        target_h = int(round(canvas_h_in * yres))

        new_left = placement_for_axis(crop_w, bx0, bx1, target_w)
        new_top = placement_for_axis(crop_h, by0, by1, target_h)

        offx = int(round(-new_left))
        offy = int(round(-new_top))

        image.resize(target_w, target_h, offx, offy)

        Gimp.context_push()
        try:
            Gimp.context_set_background(Gegl.Color.new("white"))
            for layer in image.get_layers():
                layer.resize_to_image_size()
        finally:
            Gimp.context_pop()
    finally:
        image.undo_group_end()

    Gimp.displays_flush()


def _gimp_unit_for_key(unit_key):
    return {
        "in": Gimp.Unit.inch(),
        "mm": Gimp.Unit.mm(),
        "pt": Gimp.Unit.point(),
        "pica": Gimp.Unit.pica(),
    }[unit_key]


def _key_for_gimp_unit(unit):
    for key in UNITS_PER_INCH:
        if _gimp_unit_for_key(key) == unit:
            return key
    return "in"


def show_dialog(image, config):
    GimpUi.init("resize-canvas-for-print")

    default_print_unit = config.get_property("print-unit")
    default_custom_unit = config.get_property("custom-unit")

    # print-value is stored in print-unit, not inches (RCFP-DIALOG-PERSIST-010) -
    # convert to inches for the fit/clamp computation, then back to
    # print-unit for display (RCFP-DIALOG-PERSIST-004/007).
    default_print_w_in, default_print_h_in = print_size_from_config(
        image, config.get_property("print-axis"),
        to_inches(config.get_property("print-value"), default_print_unit),
    )
    default_print_w = from_inches(default_print_w_in, default_print_unit)
    default_print_h = from_inches(default_print_h_in, default_print_unit)
    default_preset_index = config.get_property("preset-idx")

    # GimpUi.Dialog (not plain Gtk.Dialog) registers with GIMP's own
    # dialog factory - monitor-aware positioning, geometry memory, etc.
    # That alone isn't enough in every display environment though, so
    # request centering explicitly too.
    use_header_bar = Gtk.Settings.get_default().get_property("gtk-dialogs-use-header")
    dialog = GimpUi.Dialog(title="Resize Canvas for Print", role="resize-canvas-for-print",
                            use_header_bar=use_header_bar)
    dialog.set_position(Gtk.WindowPosition.CENTER)
    dialog.add_button("_Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("_OK", Gtk.ResponseType.OK)
    dialog.set_default_response(Gtk.ResponseType.OK)

    grid = Gtk.Grid(column_spacing=8, row_spacing=6, border_width=8)
    dialog.get_content_area().add(grid)

    # Layout matches GIMP's own size-entry dialogs (e.g. Canvas Size): width
    # above height, with a single unit dropdown beside the height field -
    # not a separate row of its own, and the same shape for both groups
    # below. GimpUi.SizeEntry's own bundled layout didn't reliably produce
    # this when tried (see dialog-persistence-design.md's Decisions table),
    # so both groups build it explicitly instead: plain spin buttons plus a
    # real GimpUi.UnitComboBox, wired up by hand.
    row = 0
    label = Gtk.Label(xalign=0)
    label.set_markup("<b>Print size</b>")
    grid.attach(label, 0, row, 3, 1)
    row += 1

    default_print_lower, default_print_upper = size_field_bounds(default_print_unit)
    print_w_adj = Gtk.Adjustment(value=default_print_w,
                                  lower=default_print_lower, upper=default_print_upper,
                                  step_increment=0.1, page_increment=1)
    print_h_adj = Gtk.Adjustment(value=default_print_h,
                                  lower=default_print_lower, upper=default_print_upper,
                                  step_increment=0.1, page_increment=1)
    print_w_spin = Gtk.SpinButton(adjustment=print_w_adj, digits=2)
    print_h_spin = Gtk.SpinButton(adjustment=print_h_adj, digits=2)
    # NEEDS LIVE-GIMP VERIFICATION: GimpUi.UnitComboBox has no confirmed way
    # to exclude pixels/percent (RCFP-DIALOG-UNIT-006); an unrecognized
    # selection falls back to "in" via _key_for_gimp_unit rather than
    # crashing, but pixels/percent may still be selectable in practice.
    print_unit_combo = GimpUi.UnitComboBox.new()
    print_unit_combo.set_unit(_gimp_unit_for_key(default_print_unit))

    grid.attach(Gtk.Label(label="Width:", xalign=0), 0, row, 1, 1)
    grid.attach(print_w_spin, 1, row, 1, 1)
    row += 1
    grid.attach(Gtk.Label(label="Height:", xalign=0), 0, row, 1, 1)
    grid.attach(print_h_spin, 1, row, 1, 1)
    grid.attach(print_unit_combo, 2, row, 1, 1)
    row += 1

    updating = {"flag": False}
    last_edited_axis = {"axis": config.get_property("print-axis") or None}
    current_print_unit = {"unit": default_print_unit}

    def on_w_changed(_adj):
        if updating["flag"]:
            return
        last_edited_axis["axis"] = "width"
        updating["flag"] = True
        print_h_adj.set_value(print_w_adj.get_value() * image.get_height() / image.get_width())
        updating["flag"] = False

    def on_h_changed(_adj):
        if updating["flag"]:
            return
        last_edited_axis["axis"] = "height"
        updating["flag"] = True
        print_w_adj.set_value(print_h_adj.get_value() * image.get_width() / image.get_height())
        updating["flag"] = False

    print_w_adj.connect("value-changed", on_w_changed)
    print_h_adj.connect("value-changed", on_h_changed)

    def on_print_unit_changed(combo):
        new_unit = _key_for_gimp_unit(combo.get_unit())
        old_unit = current_print_unit["unit"]
        if new_unit == old_unit:
            return
        current_print_unit["unit"] = new_unit
        axis = last_edited_axis["axis"] or "width"
        # Same re-entrancy guard on_w_changed/on_h_changed use, so this
        # conversion isn't mistaken for a user edit (RCFP-DIALOG-UNIT-003).
        updating["flag"] = True
        new_lower, new_upper = size_field_bounds(new_unit)
        print_w_adj.set_lower(new_lower)
        print_w_adj.set_upper(new_upper)
        print_h_adj.set_lower(new_lower)
        print_h_adj.set_upper(new_upper)
        if axis == "height":
            print_h_adj.set_value(from_inches(to_inches(print_h_adj.get_value(), old_unit), new_unit))
            print_w_adj.set_value(print_h_adj.get_value() * image.get_width() / image.get_height())
        else:
            print_w_adj.set_value(from_inches(to_inches(print_w_adj.get_value(), old_unit), new_unit))
            print_h_adj.set_value(print_w_adj.get_value() * image.get_height() / image.get_width())
        updating["flag"] = False

    print_unit_combo.connect("changed", on_print_unit_changed)

    grid.attach(Gtk.Separator(), 0, row, 3, 1)
    row += 1

    label = Gtk.Label(xalign=0)
    label.set_markup("<b>Output canvas</b>")
    grid.attach(label, 0, row, 3, 1)
    row += 1

    preset_combo = Gtk.ComboBoxText()
    for preset_label, _w, _h in PRESETS:
        preset_combo.append_text(preset_label)
    preset_combo.set_active(default_preset_index)
    grid.attach(preset_combo, 0, row, 3, 1)
    row += 1

    # Only meaningful in Custom mode - the user types directly into these.
    # For named presets, orientation/size is decided once, at OK time (see
    # get_canvas_size below), not live while the dialog is open. Custom's
    # width/height have no aspect lock or last-edited-axis to protect, so
    # unit conversion here doesn't need the re-entrancy guard above - both
    # fields just convert directly.
    starting_w = config.get_property("custom-width")
    starting_h = config.get_property("custom-height")
    default_custom_lower, default_custom_upper = size_field_bounds(default_custom_unit)
    custom_w_adj = Gtk.Adjustment(value=starting_w,
                                   lower=default_custom_lower, upper=default_custom_upper,
                                   step_increment=0.1, page_increment=1)
    custom_h_adj = Gtk.Adjustment(value=starting_h,
                                   lower=default_custom_lower, upper=default_custom_upper,
                                   step_increment=0.1, page_increment=1)
    custom_w_spin = Gtk.SpinButton(adjustment=custom_w_adj, digits=2)
    custom_h_spin = Gtk.SpinButton(adjustment=custom_h_adj, digits=2)
    custom_unit_combo = GimpUi.UnitComboBox.new()
    custom_unit_combo.set_unit(_gimp_unit_for_key(default_custom_unit))
    current_custom_unit = {"unit": default_custom_unit}

    custom_w_label = Gtk.Label(label="Width:", xalign=0)
    custom_h_label = Gtk.Label(label="Height:", xalign=0)
    grid.attach(custom_w_label, 0, row, 1, 1)
    grid.attach(custom_w_spin, 1, row, 1, 1)
    row += 1
    grid.attach(custom_h_label, 0, row, 1, 1)
    grid.attach(custom_h_spin, 1, row, 1, 1)
    grid.attach(custom_unit_combo, 2, row, 1, 1)
    row += 1

    custom_widgets = (custom_w_label, custom_h_label, custom_w_spin, custom_h_spin, custom_unit_combo)
    for widget in custom_widgets:
        widget.set_no_show_all(True)

    def on_preset_changed(combo):
        idx = combo.get_active()
        is_custom = PRESETS[idx][1] is None
        for widget in custom_widgets:
            widget.set_visible(is_custom)

    preset_combo.connect("changed", on_preset_changed)

    def on_custom_unit_changed(combo):
        new_unit = _key_for_gimp_unit(combo.get_unit())
        old_unit = current_custom_unit["unit"]
        if new_unit == old_unit:
            return
        current_custom_unit["unit"] = new_unit
        new_lower, new_upper = size_field_bounds(new_unit)
        custom_w_adj.set_lower(new_lower)
        custom_w_adj.set_upper(new_upper)
        custom_h_adj.set_lower(new_lower)
        custom_h_adj.set_upper(new_upper)
        custom_w_adj.set_value(from_inches(to_inches(custom_w_adj.get_value(), old_unit), new_unit))
        custom_h_adj.set_value(from_inches(to_inches(custom_h_adj.get_value(), old_unit), new_unit))

    custom_unit_combo.connect("changed", on_custom_unit_changed)

    on_preset_changed(preset_combo)
    dialog.show_all()
    response = dialog.run()

    result = None
    if response == Gtk.ResponseType.OK:
        print_unit = current_print_unit["unit"]
        custom_unit = current_custom_unit["unit"]
        # print_w_adj/print_h_adj and custom_w_adj/custom_h_adj are in
        # print_unit/custom_unit, not inches - convert before calling
        # get_canvas_size, which (like the rest of Orientation & Placement)
        # only ever works in inches (RCFP-DIALOG-UNIT-005).
        print_w_in = to_inches(print_w_adj.get_value(), print_unit)
        print_h_in = to_inches(print_h_adj.get_value(), print_unit)
        custom_w_in = to_inches(custom_w_adj.get_value(), custom_unit)
        custom_h_in = to_inches(custom_h_adj.get_value(), custom_unit)
        canvas_w_in, canvas_h_in = get_canvas_size(
            image, preset_combo.get_active(),
            print_w_in, print_h_in,
            custom_w_in, custom_h_in,
        )
        result = (print_w_in, print_h_in, canvas_w_in, canvas_h_in)
        config.set_property("print-axis", last_edited_axis["axis"] or "")
        config.set_property(
            "print-value",
            print_h_adj.get_value() if last_edited_axis["axis"] == "height" else print_w_adj.get_value(),
        )
        config.set_property("print-unit", print_unit)
        config.set_property("preset-idx", preset_combo.get_active())
        config.set_property("custom-width", custom_w_adj.get_value())
        config.set_property("custom-height", custom_h_adj.get_value())
        config.set_property("custom-unit", custom_unit)
    dialog.destroy()
    return result


class ResizeCanvasForPrint(Gimp.PlugIn):
    def do_query_procedures(self):
        return [PROC_NAME]

    def do_create_procedure(self, name):
        Gegl.init(None)

        procedure = Gimp.ImageProcedure.new(
            self, name, Gimp.PDBProcType.PLUGIN, self.run, None
        )
        procedure.set_image_types("*")
        procedure.set_menu_label("Resize Canvas for _Print...")
        procedure.add_menu_path("<Image>/Image")
        procedure.set_documentation(
            "Set print resolution and resize canvas to a standard photo size",
            "Sets the image's resolution so the current crop prints at a "
            "chosen physical size, then resizes the canvas to a standard "
            "photo size (default 4x6in), centering on the crop and pulling "
            "in extra layer data before padding with white.",
            name,
        )
        procedure.set_attribution("Chris Lahey", "Chris Lahey", "2026")

        # "print-axis" is "width", "height", or "" (never set yet).
        procedure.add_string_argument(
            "print-axis", "Print size axis last edited",
            "Which of print-width/print-height the user set explicitly last",
            "", GObject.ParamFlags.READWRITE)
        procedure.add_double_argument(
            "print-value", "Print size value", "Value of the last-edited print size axis, in inches",
            0.1, 100.0, 6.0, GObject.ParamFlags.READWRITE)
        procedure.add_int_argument(
            "preset-idx", "Output canvas preset", "Index into the canvas size preset list",
            0, len(PRESETS) - 1, 0, GObject.ParamFlags.READWRITE)
        procedure.add_double_argument(
            "custom-width", "Custom canvas width", "Custom canvas width, in inches",
            0.1, 100.0, PRESETS[0][1], GObject.ParamFlags.READWRITE)
        procedure.add_double_argument(
            "custom-height", "Custom canvas height", "Custom canvas height, in inches",
            0.1, 100.0, PRESETS[0][2], GObject.ParamFlags.READWRITE)
        procedure.add_string_argument(
            "print-unit", "Print size unit",
            "Unit print-value is stored in ('in', 'mm', 'pt', or 'pica')",
            "in", GObject.ParamFlags.READWRITE)
        procedure.add_string_argument(
            "custom-unit", "Custom canvas unit",
            "Unit custom-width/custom-height are stored in ('in', 'mm', 'pt', or 'pica')",
            "in", GObject.ParamFlags.READWRITE)

        return procedure

    def run(self, procedure, run_mode, image, drawables, config, run_data):
        if run_mode == Gimp.RunMode.INTERACTIVE:
            values = show_dialog(image, config)
            if values is None:
                return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())
            print_w, print_h, canvas_w, canvas_h = values
        else:
            # WITH_LAST_VALS (Ctrl+F) or NONINTERACTIVE (scripted): config
            # is already populated by GIMP, either with the last-used
            # values or with whatever was passed explicitly - no dialog.
            # print-value/custom-width/custom-height are stored in
            # print-unit/custom-unit, not inches (RCFP-DIALOG-PERSIST-010) -
            # convert to inches before any computation (RCFP-DIALOG-UNIT-005).
            print_value_in = to_inches(
                config.get_property("print-value"), config.get_property("print-unit"))
            print_w, print_h = print_size_from_config(
                image, config.get_property("print-axis"), print_value_in,
            )
            custom_w_in = to_inches(
                config.get_property("custom-width"), config.get_property("custom-unit"))
            custom_h_in = to_inches(
                config.get_property("custom-height"), config.get_property("custom-unit"))
            canvas_w, canvas_h = get_canvas_size(
                image, config.get_property("preset-idx"), print_w, print_h,
                custom_w_in, custom_h_in,
            )

        run_resize_canvas_for_print(image, print_w, print_h, canvas_w, canvas_h)

        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


if __name__ == "__main__":
    Gimp.main(ResizeCanvasForPrint.__gtype__, sys.argv)
