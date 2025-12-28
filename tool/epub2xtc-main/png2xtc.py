#!/usr/bin/env python3
"""
Convert a folder of PNGs (480x800) to a single XTC file with proper little-endian header.
"""
import sys
import os
import struct
import hashlib
from PIL import Image

def png_to_xtg_bytes(img: Image.Image, force_size=(480,800), threshold=200):
    """Convert PIL image to XTG bytes (1-bit monochrome)."""
    if img.size != force_size:
        img = img.resize(force_size, Image.LANCZOS)

    w, h = img.size
    gray = img.convert("L")
    row_bytes = (w + 7) // 8
    data = bytearray(row_bytes * h)

    pixels = gray.load()
    for y in range(h):
        for x in range(w):
            bit = 1 if pixels[x, y] >= threshold else 0
            byte_index = y * row_bytes + (x // 8)
            bit_index = 7 - (x % 8)  # MSB first
            if bit:
                data[byte_index] |= (1 << bit_index)

    md5digest = hashlib.md5(data).digest()[:8]
    data_size = len(data)

    # XTG header: <4sHHBBI8s> little-endian
    header = struct.pack(
        "<4sHHBBI8s",
        b"XTG\x00",
        w,
        h,
        0,  # colorMode
        0,  # compression
        data_size,
        md5digest
    )
    return header + data

def build_xtc(png_paths, out_path, read_direction=0, thumbnail=0, force_size=(480,800)):
    """Build a proper XTC file."""
    xtg_blobs = []
    for p in png_paths:
        img = Image.open(p)
        xtg_blobs.append(png_to_xtg_bytes(img, force_size))

    page_count = len(xtg_blobs)
    header_size = 48
    index_entry_size = 16
    index_offset = header_size
    data_offset = index_offset + page_count * index_entry_size



    # Index table: <Q I H H> per page
    index_table = bytearray()
    rel_offset = data_offset
    for blob in xtg_blobs:
        w, h = struct.unpack_from("<HH", blob, 4)
        entry = struct.pack("<Q I H H", rel_offset, len(blob), w, h)
        index_table += entry
        rel_offset += len(blob)

    has_thumbnail = 0 if thumbnail == 0 else 1
    if has_thumbnail:
        thumbOffset = rel_offset # TODO: properly index the correct page
        thumbnail_blob = xtg_blobs[thumbnail-1]
    else:
        thumbOffset = 0

    # XTC header: <4sHHBBBBIQQQQ> little-endian
    xtc_header = struct.pack(
        "<4sHHBBBBIQQQQ",
        b"XTC\x00",         # mark
        0x0100,                  # version
        page_count,         # pageCount
        read_direction,     # readDirection
        0,                  # hasMetadata
        has_thumbnail,      # hasThumbnails
        0,                  # hasChapters
        0,                  # currentPage
        0,                  # metadataOffset
        index_offset,       # indexOffset
        data_offset,        # dataOffset
        thumbOffset         # thumbOffset
    )
    assert len(xtc_header) == 48
    print("index offset:", index_offset)
    print("data offset:", data_offset)
    print("header:", xtc_header)
    # Write file
    with open(out_path, "wb") as f:
        f.write(xtc_header)
        f.write(index_table)
        for blob in xtg_blobs:
            f.write(blob)
        if has_thumbnail:
            f.write(thumbnail_blob)

    print(f"Wrote XTC ({page_count} pages) to {out_path}")

def write_xtg_file(png_path: str, xtg_out_path: str, force_size=(480, 800), threshold=128):
    """
    Convert a single PNG to an XTG file using the existing png_to_xtg_bytes function.
    """
    # Use the existing function to generate the XTG bytes
    xtg_bytes = png_to_xtg_bytes(
        Image.open(png_path),
        force_size=force_size,
        threshold=threshold
    )

    # Write the bytes to file
    with open(xtg_out_path, "wb") as f:
        f.write(xtg_bytes)

    print(f"Wrote XTG page to {xtg_out_path}")

def main():
    if len(sys.argv) < 3:
        print("Usage: python pngs_to_xtc.py input.png|folder output.xtc|xtg")
        sys.exit(1)
    out_file = sys.argv[2]
    if out_file[-1] == 'g':
        png = sys.argv[1]

        write_xtg_file(png, out_file)
    else:
        folder = sys.argv[1]

        pngs = sorted([os.path.join(folder, f) for f in os.listdir(folder)
                       if f.lower().endswith(".png")])
        if not pngs:
            print("No PNG files found in", folder, file=sys.stderr)
            sys.exit(1)

        build_xtc(pngs, out_file)

if __name__ == "__main__":
    main()

