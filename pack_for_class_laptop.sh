#!/bin/bash
# Copy the Sudan project, its data and the Swellendam project (site_selection_v4) to a USB stick.
#
#   bash pack_for_class_laptop.sh /media/$USER/<USB-name>
#
# Uses rsync: you can run it again after changes and it copies only what changed.
set -e
DEST="${1:?Give the USB folder, e.g. /media/$USER/MYUSB}"
[ -d "$DEST" ] || { echo "Not found: $DEST (is the USB stick mounted?)"; exit 1; }
OUT="$DEST/for_class_laptop"
mkdir -p "$OUT"

SRC_DATA="$HOME/Downloads/sdn_datasets"          # data (1.6 GB) + sudan_site_analysis + fromClass
SRC_V4="$HOME/Desktop/site_selection_v4"         # Swellendam project

need=$(du -sb "$SRC_DATA" "$SRC_V4" 2>/dev/null | awk '{s+=$1} END {print s}')
free=$(df -B1 --output=avail "$DEST" | tail -1)
echo "To copy: $((need / 1024 / 1024)) MB, free on USB: $((free / 1024 / 1024)) MB"
[ "$need" -lt "$free" ] || { echo "Not enough space on the USB stick."; exit 1; }

# FAT32 sticks cannot hold files over 4 GB; nothing here is that big, but they also
# do not keep Linux permissions, so --no-perms avoids warnings.
rsync -rt --no-perms --info=progress2 --exclude='__pycache__' "$SRC_DATA" "$OUT/"
[ -d "$SRC_V4" ] && rsync -rt --no-perms --info=progress2 --exclude='__pycache__' "$SRC_V4" "$OUT/" \
                  || echo "NOTE: $SRC_V4 not found - skipped"
cp "$SRC_DATA/sudan_site_analysis/unpack_on_class_laptop.sh" "$OUT/"
sync
echo
echo "Done. On the class laptop:  bash /media/\$USER/<USB-name>/for_class_laptop/unpack_on_class_laptop.sh"
