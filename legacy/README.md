# Legacy Spartina Prototype — Historical Archive

This directory preserves the **early Spartina project code and diagrams**
created before the Spartina Earth reboot (M0, 2026-09).

## Status and rules

1. These files originate from an early, exploratory Spartina alterniflora
   project (originally developed on a local Windows workstation; all paths
   in the code are Windows paths such as `D:\Spatina Test`).
2. They are retained **for historical traceability only**. Nothing was
   deleted during the M0 repository reboot; files were relocated with
   `git mv` so full history is preserved.
3. **None of this code has been re-validated under current research
   standards.** Dependency sets, data paths, and correctness are all
   treated as `UNVERIFIED`.
4. This code does **not** constitute a current or formal experimental
   result.
5. **Do not cite any metric, accuracy, IoU, or other number implied or
   produced by this legacy code as a result in any new manuscript.**
   No quantitative results (no trained checkpoint, no log, no metric
   table) were found alongside this code in the repository; see
   [`../docs/audit/LEGACY_RESULT_AUDIT.md`](../docs/audit/LEGACY_RESULT_AUDIT.md).

## Layout

| Path | Original file | Content (observed from source) |
|---|---|---|
| `image_collection/` | `1 Image capture.py` | Selenium scraper for Google Images of "Spartina alterniflora" (max 10 images downloaded) |
| `classification/` | `2 CNN Set Up.py` | TensorFlow/Keras binary CNN (224×224, 5 epochs); note only the `spartina` class folder is ever populated; `other` is created but never filled |
| `segmentation/` | `3 U-NET.py` | PyTorch U-Net training sketch; references undefined variables `images, masks`; decoder does not use skip connections; not runnable as committed |
| `segmentation/` | `11 mask build.py` | Empty file (0 bytes) |
| `annotations/` | `4 coco json process.py` | Overlays COCO polygons on images with pycocotools |
| `annotations/` | `8 coco json information.py` | Prints top-level structure of a COCO JSON |
| `annotations/` | `9 coco json adjust.py` | Pads images to 2048×1367 and shifts COCO coordinates/bboxes |
| `annotations/` | `10 image show.py` | Visualizes COCO polygons and bboxes for padded images |
| `preprocessing/` | `5 data set preparatioin.py` | Rasterizes COCO polygons to masks and performs a **random image-level 70/15/15 split** (spatial-disjointness not guaranteed — forbidden under the current benchmark contract) |
| `preprocessing/` | `6 image size test.py` | Lists `.jpg` image dimensions; computes max width/height |
| `preprocessing/` | `7 image adjust.py` | Pads images with black borders to 2048×1367 |
| `diagrams/` | `Spartina.drawio`, `Spatina Net.drawio`, `未命名绘图.drawio` | Early DrawIO architecture/process sketches |
| `play.py` | `play.py` | Trivial scratch script (prints a random integer 1–30) |
| `README.original.md` | original root `README.md` | Verbatim copy of the pre-reboot one-line README |

## Known legacy data dependencies (not present in this repository)

- `D:\Spatina Test\cocojson.json` and images under `D:\Spatina Test`
- `D:\SpartinaDataset` (output of the preparation script)
- `spartina_images/` and `spartina_model.h5` (runtime artifacts of scripts 1–2)

These are Windows-local paths. As of M0, no corresponding COCO JSON,
image set, or checkpoint has been located in this repository or recorded
in the data inventory. If such data is found later (e.g. under
`old datasets/` or external storage), it must be inventoried and audited
before use; it does not automatically become validated.
