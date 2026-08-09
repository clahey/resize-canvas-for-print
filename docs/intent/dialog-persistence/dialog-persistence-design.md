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

## Persistence

The dialog's settings are declared as real PDB procedure arguments — `print-axis`, `print-value`, `preset-idx`, `custom-width`, `custom-height` — bound to the `config` object GIMP passes into `run()`, rather than kept in a private file. GIMP's own last-used-values mechanism then handles both pre-filling the dialog on reopen and driving `WITH_LAST_VALS` (GIMP's "repeat last filter," e.g. Ctrl+F) to run without showing the dialog at all.

Only the last *edited* print-size axis is remembered, not both numbers. The print width and height are locked together by the current crop's aspect ratio, and a different photo's crop will rarely share that exact ratio — so remembering both numbers from a prior session would usually produce an inconsistent pair. Instead, only which axis (width or height) was last typed, and its value, is remembered; the other axis is always re-derived from the *current* crop's aspect ratio, and the remembered value is clamped to the largest size that fits the current crop without forcing a crop.

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

## Open Questions & Future Decisions

### Deferred
1. **Unit selection** (inches/cm/mm/etc.) for the print-size and custom-canvas fields, including a full paper-size preset list, and automatic conversion of the displayed value when the unit changes. Not yet implemented; an investigated approach is recorded below so the work doesn't need to be re-investigated from scratch.

   - **Widget**: `GimpUi.SizeEntry`, a composite widget pairing one or more numeric fields with a single shared unit dropdown. Changing the dropdown converts the field's displayed value in place, which covers the automatic-conversion requirement without custom conversion math.
   - **Rejected building block**: `GimpUi.UnitComboBox` alone — just the unit dropdown, with no field-conversion behavior of its own — was considered and rejected in favor of `GimpUi.SizeEntry`, which provides that conversion for free.
   - **Integration with the existing fields**: rather than replacing the print-size and Custom width/height spin buttons, a `GimpUi.SizeEntry` would wrap each via `add_field(spin_button, ...)`, with `show_refval=False` (the entry should not also draw its own duplicate numeric field alongside the existing spin button) and `update_policy=NONE` (the entry should not overwrite field values on its own; resolution changes stay managed explicitly by the plugin, per `RCFP-DIALOG-APPLY-001`).
   - **Two independent groups**: the dialog has two size groups — print size and Custom canvas size — and a single `GimpUi.SizeEntry` instance only drives one shared unit dropdown for its own fields, so this would need two separate instances. Keeping their two unit dropdowns in sync with each other (so picking cm in one switches the other) is not automatic and would need an explicit signal connection between the two instances.
   - Reference consulted for `add_field`/`show_refval`/`update_policy` semantics: the `GimpSizeEntry` C API reference, https://www.manpagez.com/html/libgimpwidgets/libgimpwidgets-2.10.34/GimpSizeEntry.php (PyGObject exposes the same properties/methods; no Python-specific documentation for this widget was found).

## References

- HLD: `docs/high-level-design.md`
- GIMP bundled example plugins consulted: `foggify.py`, `goat-exercise-py3.py`, `spyro-plus.py`
- `GimpSizeEntry` C API reference: https://www.manpagez.com/html/libgimpwidgets/libgimpwidgets-2.10.34/GimpSizeEntry.php
