# Dialog & Persistence — EARS Specs

## UI

- [x] **RCFP-DIALOG-UI-001**: The system shall construct the dialog as a `GimpUi.Dialog` with an explicit `role`, registering it with GIMP's dialog factory.
- [x] **RCFP-DIALOG-UI-002**: The system shall set the dialog's window position to centered, independent of dialog factory registration.
- [x] **RCFP-DIALOG-UI-003**: The system shall set the dialog's header-bar button placement from the `gtk-dialogs-use-header` GTK setting rather than a hardcoded value.
- [x] **RCFP-DIALOG-UI-004**: When the user edits the print-size width field, the system shall recompute the print-size height field from the current image's pixel aspect ratio (width ÷ height); when the user edits the height field, the system shall recompute the width field the same way.
- [x] **RCFP-DIALOG-UI-005**: While the output-canvas selection is a named preset, the system shall hide the Custom width/height fields.
- [x] **RCFP-DIALOG-UI-006**: While the output-canvas selection is Custom, the system shall show the Custom width/height fields.

## Persistence

- [x] **RCFP-DIALOG-PERSIST-001**: The system shall declare `print-axis`, `print-value`, `preset-idx`, `custom-width`, and `custom-height` as PDB procedure arguments bound to GIMP's `ProcedureConfig`, rather than a private settings file.
- [x] **RCFP-DIALOG-PERSIST-002**: When the user directly edits a print-size field (not as a result of the aspect-lock recompute triggered by editing the other field), the system shall record which axis, width or height, was edited.
- [x] **RCFP-DIALOG-PERSIST-003**: When the dialog is confirmed, the system shall persist the last-edited print-size axis and its current value to `print-axis`/`print-value`, and the current preset index and Custom width/height to `preset-idx`/`custom-width`/`custom-height`.
- [x] **RCFP-DIALOG-PERSIST-004**: When the dialog opens, the system shall set the persisted last-edited axis's print-size field to the minimum of its persisted value and the largest size that fits the current crop without cropping it, and shall derive the other axis's field from the current crop's aspect ratio.
- [x] **RCFP-DIALOG-PERSIST-005**: When invoked via GIMP's repeat-last-filter (`WITH_LAST_VALS`) or a script (`NONINTERACTIVE`), the system shall read the persisted values from `config` and apply them without showing the dialog.

## Apply

- [x] **RCFP-DIALOG-APPLY-001**: When the dialog (or a scripted/repeat invocation) is confirmed, the system shall set the image's resolution from the chosen print size and the crop's pixel dimensions.
- [x] **RCFP-DIALOG-APPLY-002**: The system shall resize the image canvas to the canvas extent and position decided by the orientation/placement algorithm (see RCFP-ORIENT).
- [x] **RCFP-DIALOG-APPLY-003**: After resizing the canvas, the system shall resize every layer to the new canvas size with the background color set to white, so canvas area not covered by existing layer content becomes opaque white.
- [x] **RCFP-DIALOG-APPLY-004**: When resizing a layer to the new canvas size, the system shall preserve existing transparency within that layer's prior bounds.
