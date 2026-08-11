---
parent: high-level-design
prefix: RCFP-DIALOG
---

# Dialog & Persistence

## Context and Design Philosophy

This component is the interactive shell around the Orientation & Placement algorithm: it collects the print size and paper choice from the user (or, when invoked via GIMP's "repeat last filter" or a script, skips the dialog entirely and reads previously-saved values), then applies the decided sizes to the image. Its guiding tenet is matching GIMP's own dialog and persistence conventions rather than inventing custom equivalents, so the plugin behaves like a native part of GIMP.

## Dialog Construction

The dialog is a custom `GimpUi.Dialog`-based `Gtk.Grid` layout, not the auto-generated `GimpProcedureDialog` GIMP can build from declared procedure arguments — the auto-generated dialog has no way to express this dialog's aspect-lock or conditional field visibility.

`GimpUi.Dialog` (not plain `Gtk.Dialog`) registers with GIMP's own dialog factory, giving monitor-aware positioning and geometry memory; it's constructed with an explicit `role` for that registration, plus an explicit `Gtk.WindowPosition.CENTER` as a fallback for display environments where factory registration alone isn't sufficient. Header-bar button placement is read from `Gtk.Settings.get_default().get_property("gtk-dialogs-use-header")` and passed as `use_header_bar`, so the dialog matches whatever convention the user's other GIMP dialogs already follow instead of assuming one.

## Print Size Fields

Width and height spin buttons are locked to the current crop's pixel aspect ratio (`image.get_width() / image.get_height()`): editing either field recomputes the other directly from the live image dimensions on every edit, rather than from a value cached at dialog-open time, so the lock stays correct even if nothing else about the crop is assumed static.

## Output Canvas Selection

A preset dropdown offers the named paper sizes (4x6, 5x7, 8x10) plus Custom. Selecting Custom reveals its own width/height fields; selecting a named preset hides them. The fields use `no_show_all` plus explicit `set_visible` calls, since `Gtk.Widget.show_all()` otherwise forces every child visible regardless of a prior `set_visible(False)`, which would briefly size the window for fields that are about to be hidden again.

Orientation for a named preset is not decided inside the dialog. It's decided once, at OK time, against whichever print size and paper choice the user ends up with — see the Orientation & Placement LLD.

## Units

Print size and the Custom canvas size each show their own unit dropdown and convert independently — picking mm for print size has no effect on the Custom canvas fields' unit, and vice versa. The two groups already accept independently-chosen numeric values (a print size in inches next to a custom paper size in mm is a legitimate combination), so keeping their unit dropdowns in sync would add a synchronization mechanism for a constraint that doesn't actually exist.

Both dropdowns are restricted to GIMP's built-in physical length units — inches, mm, points, picas (GIMP has no built-in centimeter unit) — via a `GimpUi.UnitStore` with `set_has_pixels(False)`/`set_has_percent(False)`, passed to the dropdown through `GimpUi.UnitComboBox.new_with_model`. `UnitComboBox.new()` alone defaults to a store that includes pixels, percent, and any user-defined units; pixels and percent are excluded because a physical print or paper size doesn't have an unambiguous meaning in either (percent-of-what; pixels only convert to a physical size via the resolution this dialog is itself computing).

Conversion math (`to_inches`/`from_inches`) works off `Gimp.Unit.get_factor()` directly rather than a plugin-maintained table of unit factors — the unit values it operates on come straight from the dropdown (`GimpUi.UnitComboBox.get_active()` returns a `Gimp.Unit`) or from config, so there's no separate list of "units the plugin knows about" to keep in sync with what the dropdown actually offers.

Preset labels (e.g. "4 x 6 in") always display in inches regardless of the selected print-size unit — `PRESETS`' physical sizes are fixed in inches internally, and the labels aren't run through unit conversion. Orientation & Placement's pure functions (`best_orientation`, `get_canvas_size`, `placement_for_axis`) are likewise unaffected by unit selection: they only ever see values already converted to inches (see Persistence, below).

**Layout.** Both groups lay out as width above height, with a single `GimpUi.UnitComboBox` beside the height field — matching the layout GIMP's own size-entry dialogs (e.g. Canvas Size) use, and identical between the two groups. `GimpUi.SizeEntry`'s own bundled layout is a single composite widget with no supported way to extract just the dropdown while driving externally-laid-out fields, or to keep one of its own fields invisible while showing only the dropdown — and didn't reliably reproduce this width-above-height shape when tried. Both groups instead use plain `Gtk.SpinButton`s laid out directly in the dialog's own grid, plus a real `GimpUi.UnitComboBox` wired up by hand — giving full control over the layout, and matching it exactly between the two groups.

**Conversion.** On the unit dropdown's `changed` signal, the plugin converts the affected field(s)' values from the previous unit to the new one, using the same inch-based conversion the rest of the plugin uses (see Persistence, below):

- **Custom canvas size** has no other cross-field bookkeeping, so both width and height convert directly.
- **Print size** has two pieces of cross-field bookkeeping that already assume every `value-changed` event on the width/height fields is a genuine user edit: the aspect lock (editing one field recomputes the other from the live crop ratio) and the last-edited-axis persistence (see Persistence, below). Only the field last edited directly (the same axis tracked for persistence, defaulting to width before either has been edited) is converted; the write goes through the same re-entrancy guard the aspect lock uses, so its normal side effect re-derives the other field from the live crop ratio exactly as a real edit would, without the last-edited-axis tracking mistaking the conversion for one.

**Field bounds.** Both groups' width/height fields have their min/max bounds fixed in inches (`SIZE_FIELD_LOWER_IN`/`SIZE_FIELD_UPPER_IN`) and converted to the current unit, rather than a single flat range reused verbatim in every unit — a flat 0.1–100 range, for instance, would cap print size at well under an inch in points. The bounds are recomputed on every unit change alongside the fields' displayed values.

Separately, `print-value`/`custom-width`/`custom-height`'s own PDB argument bounds (independent of the GTK fields' bounds above) are declared generously wide rather than a per-unit range, since these values are stored in whatever unit was selected (see Persistence, below) and the PDB argument itself has no way to know which unit's range applies at declaration time.

## Persistence

The dialog's settings are declared as real PDB procedure arguments — `print-axis`, `print-value`, `preset-idx`, `custom-width`, `custom-height`, `print-unit`, `custom-unit` — bound to the `config` object GIMP passes into `run()`, rather than kept in a private file. GIMP's own last-used-values mechanism then handles both pre-filling the dialog on reopen and driving `WITH_LAST_VALS` (GIMP's "repeat last filter," e.g. Ctrl+F) to run without showing the dialog at all.

Only the last *edited* print-size axis is remembered, not both numbers. The print width and height are locked together by the current crop's aspect ratio, and a different photo's crop will rarely share that exact ratio — so remembering both numbers from a prior session would usually produce an inconsistent pair. Instead, only which axis (width or height) was last typed, and its value, is remembered; the other axis is always re-derived from the *current* crop's aspect ratio, and the remembered value is clamped to the largest size that fits the current crop without forcing a crop.

`print-unit` and `custom-unit` remember each group's own last-selected display unit, independent of each other and of GIMP's global default unit. They're declared via `add_unit_argument` — a `Gimp.Unit`-valued PDB argument — so `config` hands back the actual `Gimp.Unit` directly; nothing in the plugin maintains its own mapping between a persisted representation and a live unit object. `print-value`, `custom-width`, and `custom-height` are stored in their group's own remembered unit, not in inches — the same value the visible field last showed, with no conversion at persist time. Anywhere this stored value feeds Orientation & Placement's inches-based computation (dialog prefill, OK-time, and the `WITH_LAST_VALS`/`NONINTERACTIVE` paths that skip the dialog entirely), it's converted from `print-unit`/`custom-unit` to inches first, via `Gimp.Unit.get_factor()`; the pure computation functions themselves never see a non-inches value.

## Apply

`run_resize_canvas_for_print` sets the image's resolution, resizes the canvas per the Orientation & Placement decision, then resizes every layer to the new canvas size with the background color forced to white. Newly-exposed canvas area (outside a layer's old bounds) is filled opaque white; pixels already transparent inside a layer's old bounds stay transparent. Content beyond the new canvas bounds is cropped, matching the equivalent manual GIMP operation.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Dialog widget class | `GimpUi.Dialog` with explicit `role`, plus explicit `Gtk.WindowPosition.CENTER` | Plain `Gtk.Dialog`; `GimpUi.Dialog` registration alone, with no explicit positioning | Plain `Gtk.Dialog` isn't registered with GIMP's dialog factory at all, so it gets no monitor-aware positioning. `GimpUi.Dialog` registration alone was not sufficient to center the window in the display environment tested against, so explicit centering stayed as a fallback. |
| Header-bar button placement | Read `Gtk.Settings.get_default().get_property("gtk-dialogs-use-header")`, pass as `use_header_bar` | Hardcode `use_header_bar=True`; leave it unset | Hardcoding ignores the user's actual desktop/GTK preference. Leaving it unset doesn't match GIMP's own dialogs, which read this same setting. |
| Auto-generated vs. custom dialog | Custom `Gtk.Grid` layout | `GimpProcedureDialog`, auto-generated from the declared procedure arguments | The auto-generated dialog has no mechanism for the print-size aspect lock or the Custom-mode conditional field visibility this dialog needs. |
| Settings persistence | Declared PDB procedure arguments, read/written via `config` | A private JSON settings file in the user's config directory | A private file works but doesn't participate in GIMP's own `WITH_LAST_VALS` (Ctrl+F) mechanism; declaring real arguments gets that behavior with no custom file I/O. |
| Print-size memory | Remember only the last-*edited* axis and its value, clamped to fit the current crop; always re-derive the other axis fresh | Remember both width and height directly | The edited axis holds the value the user actually chose, often a round number; the other axis is only ever a derived approximation from the crop's aspect ratio. Remembering both would preserve that approximation as if it were equally intentional — and since a different photo's crop will rarely share the exact aspect ratio of the remembered pair, the two numbers would usually end up mutually inconsistent besides. |
| Newly-exposed canvas area | Resize every layer to the new canvas size with the background forced white | `Image.flatten()`; add a new fully-opaque white layer at the bottom of the stack, sized to the canvas | Flattening merges multiple layers into one, which the equivalent manual GIMP operation (Canvas Size's "Resize layers: All") does not do. A bottom white layer would produce the same visible result without cropping existing layers' off-canvas content, but resizing every layer is what the manual workflow it's matching actually does. |
| Print size vs. Custom canvas unit dropdowns | Independent, not synced | An explicit signal connection keeping both unit widgets on the same unit | The two groups already accept independently-chosen values (e.g. print size in inches, custom paper size in mm); syncing them would add machinery for a constraint that doesn't exist. |
| Unit widget, both groups | Plain `Gtk.SpinButton`s laid out by hand, plus a real `GimpUi.UnitComboBox` (backed by a restricted `GimpUi.UnitStore`); the plugin drives conversion itself on the dropdown's `changed` signal, using the selected `Gimp.Unit`'s own `get_factor()` | `GimpUi.SizeEntry` owning its own field(s) and unit menu, for one or both groups; a hidden `SizeEntry` field mirroring the last-edited axis, for print size specifically; a plugin-maintained table of unit factors instead of `get_factor()` | `GimpSizeEntry` bundles its spin button(s) and unit dropdown into one composite widget with a fixed internal layout that didn't reproduce GIMP's own width-above-height-with-trailing-dropdown convention when tried, and offered no way to keep print size's aspect-lock/last-edited-axis bookkeeping working. Driving plain spin buttons and a real unit dropdown by hand gives full control over layout and event handling. A plugin-maintained factor table would only ever cover units the plugin's author thought to hardcode; `get_factor()` handles whatever the dropdown actually offers. |
| Size field bounds, both groups | Fixed in inches, converted to the current unit on every unit change | A single flat numeric range (e.g. 0.1-100) reused as-is regardless of unit | A flat range in every unit isn't equivalent across units — e.g. a 100-unit upper bound is under 1.4 inches in points, which breaks ordinary print sizes. |
| Display-unit persistence | New `print-unit`/`custom-unit` PDB arguments, one per group | Rely on GIMP's global default-unit preference; don't persist at all | The two groups' units are already independent (see Units, above); relying on one shared global default would re-couple them across sessions. New per-group arguments cost no custom file I/O, consistent with how the rest of this dialog's settings persist. |
| Persisted representation of `print-unit`/`custom-unit` | `add_unit_argument` — a native `Gimp.Unit`-valued PDB argument, so `config` hands back the live unit directly | `add_string_argument` storing an abbreviation (e.g. `"mm"`), with a plugin-maintained table mapping abbreviations to `Gimp.Unit` instances | The string-plus-table approach only round-trips whatever units the plugin's author thought to hardcode into the table; a live conversion (`Gimp.Unit.get_active()` on the dropdown, `.get_factor()` for the math) already needed no such table, and a unit-typed PDB argument extends that to persistence too, with no separate lookup structure to keep in sync with what the dropdown actually offers. |
| Stored value's unit | `print-value`/`custom-width`/`custom-height` are stored in their group's own remembered unit (`print-unit`/`custom-unit`), converted to inches only at the point of use | Always store in inches, converting for display only | Keeps the persisted number identical to what the field last showed, with no double bookkeeping between the display's own state and a separately-maintained inches shadow value. |
| Which units are offered | GIMP's built-in physical length units only: inches, mm, points, picas | Every unit GIMP's size widgets support by default, including pixels and percent; registering a custom cm unit at runtime | Pixels and percent don't have an unambiguous physical meaning for a print or paper size here. GIMP has no built-in centimeter unit; registering one as a custom `GimpUnit` was considered and rejected as unnecessary complexity — GIMP's own built-in set (inches, mm, points, picas) already covers metric and imperial without it. |

## Open Questions & Future Decisions

### Deferred
1. **Full paper-size preset list.** `PRESETS` currently covers 4x6/5x7/8x10/Custom; a broader standard paper-size list (A-series, other common photo sizes, etc.) is out of scope for the units work and deferred separately.
2. **Unit dropdown display (abbreviation collapsed, full name expanded).** GIMP's own unit dropdowns show a short abbreviation ("in") in the closed state and the full unit name ("inches") in the open list. Whether `GimpUi.UnitComboBox` reproduces this automatically hasn't been confirmed against a running GIMP. If it doesn't, matching it would need a custom cell-renderer setup on the dropdown; not yet investigated.

## References

- HLD: `docs/high-level-design.md`
- GIMP bundled example plugins consulted: `foggify.py`, `goat-exercise-py3.py`, `spyro-plus.py`
- `GimpSizeEntry` C API reference: https://www.manpagez.com/html/libgimpwidgets/libgimpwidgets-2.10.34/GimpSizeEntry.php
