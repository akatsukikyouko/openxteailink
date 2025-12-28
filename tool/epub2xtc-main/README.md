# Tools to generate XTC ebooks for XTeink ereaders

## Prerequisites

Requires pillow. On MacOS, install e.g. via `brew install pillow`.

## Usage

```bash
python3 png2xtc.py <input> <output>
```

where

- `<input>` can be a single .png file or a folder of .png files
- `<output>` is the name of the XTC or XTG file (XTG for single image)

## Sample toolchain to convert epub to XTC

See `epub2xtc.sh`.

Run via
```bash
./epub2xtc.sh input.epub output.xtc
```

The script requires
1. Calibre (for ebook-convert)
2. mu-tools (faster) or ImageMagick (to convert PDF to PNG) 

## Status / TODOs

- [x] Convert single PNG to black&white XTG
- [x] Convert folder of PNGs to XTC
- [ ] Convert to grayscale (2bit per pixel) to XTH
- [ ] Implement Thumbnails in XTC
- [ ] Implement Metadata in XTC
- [ ] Implement Chapter Structure in XTC

