# Dialog & Persistence — EARS Specs

## UI

- [x] **RCFP-DIALOG-UI-001**: The system shall construct the dialog as a `GimpUi.Dialog` with an explicit `role`, registering it with GIMP's dialog factory.
- [x] **RCFP-DIALOG-UI-002**: The system shall set the dialog's window position to centered.
- [x] **RCFP-DIALOG-UI-003**: The system shall set the dialog's header-bar button placement from the `gtk-dialogs-use-header` GTK setting.
- [x] **RCFP-DIALOG-UI-004**: When the user edits the print-size width field, the system shall recompute the print-size height field from the current image's pixel aspect ratio (width ÷ height); when the user edits the height field, the system shall recompute the width field the same way.
- [x] **RCFP-DIALOG-UI-005**: While the output-canvas selection is a named preset, the system shall hide the Custom width/height fields.
- [x] **RCFP-DIALOG-UI-006**: While the output-canvas selection is Custom, the system shall show the Custom width/height fields.
- [x] **RCFP-DIALOG-UI-007**: For both the print-size group and the Custom canvas-size group, the system shall lay out the width field above the height field, with that group's unit selector beside the height field — matching the layout convention GIMP's own size-entry dialogs use, and identical between the two groups.

## Persistence

- [x] **RCFP-DIALOG-PERSIST-001**: The system shall declare `print-axis`, `print-value`, `preset-idx`, `custom-width`, `custom-height`, `print-unit`, and `custom-unit` as PDB procedure arguments bound to GIMP's `ProcedureConfig`.
- [x] **RCFP-DIALOG-PERSIST-002**: When the dialog is confirmed, the system shall persist to `print-axis`/`print-value` whichever print-size axis (width or height) the user most recently edited directly, and its current value — a field's value changing only via the aspect-lock recompute triggered by editing the other field, or via a print-size unit conversion (RCFP-DIALOG-UNIT-003), does not count as editing it.
- [x] **RCFP-DIALOG-PERSIST-003**: When the dialog is confirmed, the system shall persist the current preset index and Custom width/height to `preset-idx`/`custom-width`/`custom-height`.
- [x] **RCFP-DIALOG-PERSIST-004**: When the dialog opens and a print-size axis has been persisted, the system shall compare the persisted value (converted from `print-unit` to inches) against the largest size that fits the current crop without cropping it, set that axis's print-size field to the smaller of the two (converted back to `print-unit`), and shall derive the other axis's field from the current crop's aspect ratio.
- [x] **RCFP-DIALOG-PERSIST-005**: When invoked via GIMP's repeat-last-filter (`WITH_LAST_VALS`) or a script (`NONINTERACTIVE`), the system shall read the persisted values from `config` and apply them without showing the dialog.
- [x] **RCFP-DIALOG-PERSIST-006**: When the dialog opens, the system shall default the output-canvas preset dropdown to the persisted `preset-idx`, and the Custom width/height fields to the persisted `custom-width`/`custom-height` (displayed in the persisted `custom-unit`, with no conversion, since both are stored in that same unit).
- [x] **RCFP-DIALOG-PERSIST-007**: When the dialog opens and no print-size axis has been persisted (the first run), the system shall default the print-size fields to the largest size that fits the current crop within the primary preset (the first entry in the preset list) without cropping it, converted to `print-unit`.
- [x] **RCFP-DIALOG-PERSIST-008**: The system shall declare `preset-idx`'s default as the primary preset (index 0), `custom-width`/`custom-height`'s defaults as the primary preset's width and height, and `print-unit`/`custom-unit`'s defaults as inches, so that on the first run — before anything has been persisted — the dialog opens to the primary preset with Custom's fields pre-filled to its dimensions in inches.
- [x] **RCFP-DIALOG-PERSIST-009**: When the dialog is confirmed, the system shall persist the print-size unit selector's current value to `print-unit`, and the Custom canvas-size unit selector's current value to `custom-unit`.
- [x] **RCFP-DIALOG-PERSIST-010**: The system shall persist `print-value`, `custom-width`, and `custom-height` in the unit each field displayed at the moment of persistence (`print-unit` for `print-value`, `custom-unit` for the other two), not converted to inches.
- [x] **RCFP-DIALOG-PERSIST-011**: When the dialog opens, the system shall set the print-size unit selector to the persisted `print-unit`, and the Custom canvas-size unit selector to the persisted `custom-unit`.

## Units

- [x] **RCFP-DIALOG-UNIT-001**: The system shall provide an independent unit selector for the print-size fields and for the Custom canvas-size fields; changing one selector's unit shall not alter the other's.
- [x] **RCFP-DIALOG-UNIT-006**: Both unit selectors shall offer GIMP's built-in physical length units only (inches, mm, points, picas), excluding pixels and percent.
- [x] **RCFP-DIALOG-UNIT-007**: The print-size and Custom canvas-size fields' minimum and maximum bounds shall be fixed in inches and converted to the field's group's currently selected unit, recomputed on every unit change, rather than a single flat numeric range reused unconverted across units.
- [x] **RCFP-DIALOG-UNIT-002**: The system shall display the output-canvas preset dropdown's labels in inches, regardless of the selected print-size unit.
- [x] **RCFP-DIALOG-UNIT-003**: When the print-size unit selector changes, the system shall convert the currently-displayed value of whichever print-size field (width or height) was most recently edited directly, from the previous unit to the new unit, and shall re-derive the other print-size field from the current crop's aspect ratio.
- [x] **RCFP-DIALOG-UNIT-004**: When the Custom canvas-size unit selector changes, the system shall convert the currently-displayed values of the Custom width and Custom height fields from the previous unit to the new unit.
- [x] **RCFP-DIALOG-UNIT-005**: Wherever a persisted print-size or Custom canvas-size value is used in inches-based computation (dialog prefill, OK-time canvas/orientation decisions, or a `WITH_LAST_VALS`/`NONINTERACTIVE` invocation), the system shall convert that value from its persisted unit (`print-unit`/`custom-unit`) to inches first.

## Apply

- [x] **RCFP-DIALOG-APPLY-001**: When the dialog (or a scripted/repeat invocation) is confirmed, the system shall set the image's resolution from the chosen print size and the crop's pixel dimensions.
- [x] **RCFP-DIALOG-APPLY-002**: The system shall resize the image canvas to the canvas extent for the confirmed output-canvas choice — RCFP-ORIENT's orientation decision for a named preset, or the user's typed width/height directly for Custom — at the position RCFP-ORIENT's placement decision produces for that extent, which applies to both paths.
- [x] **RCFP-DIALOG-APPLY-003**: After resizing the canvas, the system shall resize every layer to the new canvas size with the background color set to white, so canvas area not covered by existing layer content becomes opaque white.
- [x] **RCFP-DIALOG-APPLY-004**: When resizing a layer to the new canvas size, the system shall preserve existing transparency within that layer's prior bounds.
- [x] **RCFP-DIALOG-APPLY-005**: The system shall evaluate RCFP-ORIENT's orientation decision only once — when the dialog is confirmed, or when an equivalent non-interactive invocation runs — using the print size and preset selection in effect at that moment, not repeatedly while the dialog is open and unconfirmed.
