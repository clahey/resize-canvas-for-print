---
parent: high-level-design
prefix: RCFP-ORIENT
---

# Orientation & Placement

## Context and Design Philosophy

Given a chosen print size (physical inches the crop will print at) and a chosen paper size, this component decides which of the paper's two orientations to use and exactly where to position the resized canvas relative to the current crop and any extra non-destructively-cropped layer data. It is the part of the plugin that turns a paper choice into concrete pixel placement.

The controlling principle is the HLD's primary tenet: losing part of the user's deliberate crop is categorically worse than padding with white or leaving available layer margin unused. Every comparison in this component is built to reflect that ordering, not a symmetric "smallest total deviation" metric.

## Inputs

- **Crop dimensions** — the current image's pixel width/height (`image.get_width()`/`get_height()`), i.e. the print's own pixel size.
- **Layer bounding box (bbox)** — the union of all *visible* layers' extents (`get_visible_layers_bbox`), in image coordinates. When a crop was made non-destructively, this can be larger than the crop itself, exposing extra photo data the crop didn't select.
- **Print size** — the physical size, in inches, the crop's pixel dimensions map to. Together with the crop's pixel dimensions this fixes the resolution (`xres = crop_w / print_w_in`, and likewise for height).
- **Candidate paper orientation** — a preset's size as an unordered `(w_in, h_in)` pair; the two candidate orientations are `(w_in, h_in)` and `(h_in, w_in)`.

## Orientation Decision

This decision only applies to a named preset, which has two candidate orientations. A Custom paper size is a single width/height the user typed directly, with no orientation to choose between — it skips this decision entirely (see Canvas Size Resolution below).

For each candidate orientation, the **canvas extent** — the size in pixels that orientation would produce — is `canvas_extent = paper_size_in * resolution` per axis. This is never the crop; it's always the (candidate) output size.

**Primary criterion — crop loss.** Per axis, `crop_loss = max(0, crop_extent - canvas_extent)²`, summed across both axes. This measures pixels that would be cut from the print itself (the crop's own pixel dimensions), which is impossible to avoid by drawing on bbox margin — it's a real, unavoidable loss of the user's deliberate crop. If the two orientations differ on this total at all, the one with the lower total wins outright and nothing else is considered.

**Tie-break — weighted cost.** When crop loss is tied between the two orientations (the common case — the paper size is usually big enough, at the print's resolution, to contain the whole crop in either orientation, so none of it needs trimming regardless of orientation), compare a weighted sum of three further per-axis costs, each computed as the scale-invariant

```
cost(a, b) = (a - b)² / (a · b)   if a > b, else 0
```

which stays comparable across wildly different pixel scales, unlike a raw squared-pixel difference:

- **margin** — `cost(canvas_extent, crop_extent)`: the canvas extent is bigger than the crop, drawing on bbox data to cover the difference. Weight **3**.
- **content_loss** — `cost(bbox_extent, canvas_extent)`: bbox data exists but is left out of the canvas extent. Weight **1.5**.
- **white_space** — `cost(canvas_extent, bbox_extent)`: the canvas extent is bigger than the bbox can supply — genuine, unavoidable padding. Weight **1**.

The orientation with the lower weighted total wins; an exact tie goes to landscape.

## Placement Within an Axis

Once an axis's canvas extent is fixed (by the orientation decision above, or typed directly for a Custom size), its position is chosen by `placement_for_axis`:

- If the canvas extent fits entirely within the bbox on that axis, clamp the crop-centered ideal position into the range where the canvas extent stays inside the bbox — using bbox margin to avoid cropping the crop when there's room, but never displacing the placement further than necessary.
- If the canvas extent is bigger than the bbox on that axis (padding is unavoidable), center on the bbox instead of the crop, so the unavoidable padding is split evenly.

## Canvas Size Resolution

`get_canvas_size` is the entry point the rest of the plugin calls:

- **Custom paper size** — the user's typed width/height are used directly; no orientation decision is made (there's nothing to choose between).
- **Named preset** (4x6, 5x7, 8x10) — delegates to the orientation decision above.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Primary orientation criterion | Hard gate on pixels cropped from the print itself (`crop_loss`), decisive whenever the two orientations differ | Minimize white space against the bbox alone; match the crop's own aspect ratio alone | Whitespace-only picks the wrong orientation when the bbox is much larger than the crop — it freely uses unrelated extra layer margin in a way that changes the photo's framing far more than the crop implied. Aspect-only ignores cases where the bbox gives a clearly better fit than the crop's own shape suggests. |
| Tie-break metric | Weighted sum of three scale-invariant per-axis costs (`margin` ×3, `content_loss` ×1.5, `white_space` ×1) | Raw squared-pixel differences; log-ratio/aspect-mismatch scoring; matching the bbox's own aspect ratio alone | Raw pixel differences aren't comparable across images of very different pixel scale. Aspect/log-ratio scoring captures direction but not the actual amount of content at stake. Bbox-aspect matching alone can pick a "shape match" that still discards more content than a differently-shaped orientation would. The specific weights were tuned against worked examples — a near-square crop against a very tall source layer, and a thin sliver crop against its matching paper size — rather than derived analytically; revisit those cases if the weights change. |
| Placement within an axis | Clamp the crop-centered ideal into the bbox range when the canvas extent fits; otherwise center on the bbox | Always center on the crop, ignoring extra bbox margin; always center on the full bbox, ignoring the crop | Always centering on the crop wastes available non-destructive-crop margin that could avoid padding. Always centering on the bbox abandons the crop's framing even in cases where it isn't necessary to. |

## Open Questions & Future Decisions

### Deferred
1. Whether the weight constants (3, 1.5, 1) should become user-configurable, or stay fixed.

## References

- HLD: `docs/high-level-design.md`
