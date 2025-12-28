#!/bin/bash

# Debug flag - set to 1 to show command output, 0 to hide
DEBUG=0

# Set output redirect based on debug flag
if [ "$DEBUG" -eq 1 ]; then
    OUTPUT_REDIRECT="/dev/stdout"
else
    OUTPUT_REDIRECT="/dev/null"
fi

# Check if correct number of arguments provided
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 input.epub output.xtc"
    exit 1
fi

INPUT_EPUB="$1"
OUTPUT_XTC="$2"

# Check if input file exists
if [ ! -f "$INPUT_EPUB" ]; then
    echo "Error: Input file '$INPUT_EPUB' not found"
    exit 1
fi

# Create temporary directory for intermediate files
TEMP_DIR=$(mktemp -d)
TEMP_PDF="$TEMP_DIR/output.pdf"
TEMP_PNG_DIR="$TEMP_DIR/out_png"
mkdir -p "$TEMP_PNG_DIR"

echo "Converting EPUB to PDF..."
# 1. Convert EPUB to PDF with Calibre:
ebook-convert "$INPUT_EPUB" "$TEMP_PDF" \
    --custom-size 480x800 -u devicepixel \
    --change-justification justify \
    --pdf-hyphenate \
    --base-font-size 19 \
    --pdf-page-margin-top 4 \
    --pdf-page-margin-bottom 4 \
    --pdf-page-margin-left 2 \
    --pdf-page-margin-right 2 \
    > "$OUTPUT_REDIRECT"
    #--output-profile generic_eink_hd --use-profile-size 

echo "Converting PDF to PNG files..."
if command -v mutool &> /dev/null; then
    mutool draw -q -o "$TEMP_PNG_DIR/page-%04d.png" -r 220 -w 480 -h 800 "$TEMP_PDF"
else
    magick -density 600 "$TEMP_PDF" -resize 480x800 -gravity center -extent 480x800 -background white -alpha remove -alpha off -quality 95 "$TEMP_PNG_DIR/page-%04d.png" > "$OUTPUT_REDIRECT"
fi

echo "Converting PNGs to XTC..."
# 3. Convert PNGs to XTC
python3 png2xtc.py "$TEMP_PNG_DIR" "$OUTPUT_XTC" > "$OUTPUT_REDIRECT"

# Cleanup temporary files
if [ "$DEBUG" -eq 0 ]; then
    rm -rf "$TEMP_DIR"
else
    echo "Keeping $TEMP_DIR"
fi

echo "Conversion complete! Output saved to: $OUTPUT_XTC"

