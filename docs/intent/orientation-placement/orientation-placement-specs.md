# Orientation & Placement — EARS Specs

- [x] **RCFP-ORIENT-001**: When the selected output-canvas size is Custom, the system shall use the user's typed width and height directly, performing no orientation decision.
- [x] **RCFP-ORIENT-002**: For a named paper preset, the system shall evaluate exactly two candidate orientations — the preset's (width, height) and its swap (height, width).
- [x] **RCFP-ORIENT-003**: For each candidate orientation, the system shall compute the canvas extent per axis as that orientation's paper size in inches times the resolution (the crop's pixel dimension on that axis divided by the chosen print size in inches on that axis).
- [x] **RCFP-ORIENT-004**: For each candidate orientation, the system shall compute crop_loss as the sum, over both axes, of `max(0, crop_extent - canvas_extent)²`.
- [x] **RCFP-ORIENT-005**: If the two candidate orientations' crop_loss totals differ, then the system shall select the orientation with the lower crop_loss total and shall not evaluate the tie-break cost.
- [x] **RCFP-ORIENT-006**: While the two candidate orientations' crop_loss totals are equal, the system shall select the orientation with the lower weighted sum of margin (weight 3), content_loss (weight 1.5), and white_space (weight 1), each a per-axis cost of `(a-b)²/(a·b)` when the first argument exceeds the second and 0 otherwise, summed across both axes.
- [x] **RCFP-ORIENT-007**: If the two candidate orientations' weighted totals are also equal, then the system shall select the orientation with width ≥ height (landscape).
- [x] **RCFP-ORIENT-008**: When an axis's canvas extent is no larger than the visible-layer bounding box's extent on that axis, the system shall position the canvas on that axis by clamping the crop-centered ideal position into the range that keeps the canvas extent fully inside the bounding box.
- [x] **RCFP-ORIENT-009**: When an axis's canvas extent is larger than the visible-layer bounding box's extent on that axis, the system shall position the canvas on that axis by centering the canvas extent on the bounding box.
