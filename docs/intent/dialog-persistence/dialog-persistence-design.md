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

Both dropdowns are restricted to GIMP's built-in physical length units — inches, mm, points, picas (GIMP has no built-in centimeter unit). Pixels and percent, GIMP's other two built-in units, are excluded: a physical print or paper size doesn't have an unambiguous meaning in either (percent-of-what; pixels only convert to a physical size via the resolution this dialog is itself computing).

Preset labels (e.g. "4 x 6 in") always display in inches regardless of the selected print-size unit — `PRESETS`' physical sizes are fixed in inches internally, and the labels aren't run through unit conversion. Orientation & Placement's pure functions (`best_orientation`, `get_canvas_size`, `placement_for_axis`) are likewise unaffected by unit selection: they only ever see values already converted to inches (see Persistence, below).

**Custom canvas size.** A single `GimpUi.SizeEntry` with two of its own internal fields (width, height) replaces the separately-laid-out Custom width/height spin buttons — the entry's built-in conversion-on-unit-change drives both fields directly, and Custom's width and height are independent values with no other cross-field bookkeeping to protect. This is `SizeEntry`'s standard, well-documented usage (fields it owns and lays out itself), unlike the print-size group above.

**Print size.** `GimpSizeEntry` is a single composite widget bundling its own spin button(s) together with its unit dropdown — there's no supported way to extract just the dropdown while driving externally-laid-out fields, or to keep one of its own fields invisible while showing only the dropdown. That rules out wrapping the existing width/height spin buttons in a `SizeEntry`, since two pieces of cross-field bookkeeping already assume every `value-changed` event on those fields is a genuine user edit — the aspect lock (editing one field recomputes the other from the live crop ratio) and the last-edited-axis persistence (see Persistence, below) — and a `SizeEntry`-driven conversion would fire that same event.

Instead, the print-size unit selector is a plain `GimpUi.UnitComboBox` (just the dropdown, no bundled field). On its `changed` signal, the plugin converts the value of whichever print-size field (width or height) was most recently edited directly — the same axis tracked for persistence, defaulting to width before either has been edited — from the previous unit to the new one, using the same inch-based conversion the rest of the plugin uses (see Persistence, below), and writes the result back into that field through the existing re-entrancy guard the aspect lock uses. That guarded write's normal side effect recomputes the other visible field from the live crop ratio, exactly as a real edit would, but the guard keeps the last-edited-axis tracking from treating the conversion as a user edit.

## Persistence

The dialog's settings are declared as real PDB procedure arguments — `print-axis`, `print-value`, `preset-idx`, `custom-width`, `custom-height`, `print-unit`, `custom-unit` — bound to the `config` object GIMP passes into `run()`, rather than kept in a private file. GIMP's own last-used-values mechanism then handles both pre-filling the dialog on reopen and driving `WITH_LAST_VALS` (GIMP's "repeat last filter," e.g. Ctrl+F) to run without showing the dialog at all.

Only the last *edited* print-size axis is remembered, not both numbers. The print width and height are locked together by the current crop's aspect ratio, and a different photo's crop will rarely share that exact ratio — so remembering both numbers from a prior session would usually produce an inconsistent pair. Instead, only which axis (width or height) was last typed, and its value, is remembered; the other axis is always re-derived from the *current* crop's aspect ratio, and the remembered value is clamped to the largest size that fits the current crop without forcing a crop.

`print-unit` and `custom-unit` remember each group's own last-selected display unit, independent of each other and of GIMP's global default unit. `print-value`, `custom-width`, and `custom-height` are stored in their group's own remembered unit, not in inches — the same value the visible field last showed, with no conversion at persist time. Anywhere this stored value feeds Orientation & Placement's inches-based computation (dialog prefill, OK-time, and the `WITH_LAST_VALS`/`NONINTERACTIVE` paths that skip the dialog entirely), it's converted from `print-unit`/`custom-unit` to inches first; the pure computation functions themselves never see a non-inches value.

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
| Print-size unit widget | Plain `GimpUi.UnitComboBox`; the plugin manually converts whichever field was last edited using the same inch-based conversion used elsewhere, on the dropdown's `changed` signal | `GimpUi.SizeEntry` wrapping the visible width/height fields via `add_field`; a hidden `SizeEntry` field mirroring the last-edited axis | `GimpSizeEntry` bundles its spin button(s) and unit dropdown into one composite widget with no supported way to drive externally-laid-out fields or keep one of its own fields invisible — unworkable given this dialog's existing custom layout and aspect-lock/last-edited-axis bookkeeping. A plain dropdown plus the conversion functions the plugin already has sidesteps the uncertainty entirely. |
| Display-unit persistence | New `print-unit`/`custom-unit` PDB arguments, one per group | Rely on GIMP's global default-unit preference; don't persist at all | The two groups' units are already independent (see Units, above); relying on one shared global default would re-couple them across sessions. New per-group arguments cost no custom file I/O, consistent with how the rest of this dialog's settings persist. |
| Stored value's unit | `print-value`/`custom-width`/`custom-height` are stored in their group's own remembered unit (`print-unit`/`custom-unit`), converted to inches only at the point of use | Always store in inches, converting for display only | Keeps the persisted number identical to what the field last showed, with no double bookkeeping between the display's own state and a separately-maintained inches shadow value. |
| Which units are offered | GIMP's built-in physical length units only: inches, mm, points, picas | Every unit GIMP's size widgets support by default, including pixels and percent; registering a custom cm unit at runtime | Pixels and percent don't have an unambiguous physical meaning for a print or paper size here. GIMP has no built-in centimeter unit; registering one as a custom `GimpUnit` was considered and rejected as unnecessary complexity — GIMP's own built-in set (inches, mm, points, picas) already covers metric and imperial without it. |

## Open Questions & Future Decisions

### Deferred
1. **Full paper-size preset list.** `PRESETS` currently covers 4x6/5x7/8x10/Custom; a broader standard paper-size list (A-series, other common photo sizes, etc.) is out of scope for the units work and deferred separately.
2. **Spin button bounds.** All four size fields share a flat `lower=0.1, upper=100` `Gtk.Adjustment` range regardless of unit — e.g. a 100mm upper bound is a very different physical size than 100in. Whether and how the bounds should scale with the selected unit is undecided; out of scope for the units work itself.

## References

- HLD: `docs/high-level-design.md`
- GIMP bundled example plugins consulted: `foggify.py`, `goat-exercise-py3.py`, `spyro-plus.py`
- `GimpSizeEntry` C API reference: https://www.manpagez.com/html/libgimpwidgets/libgimpwidgets-2.10.34/GimpSizeEntry.php
