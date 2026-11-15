#!/bin/bash
# Run on the class laptop (Mint 22.3, QGIS 3.44) from the USB stick:
#
#   bash /media/$USER/<USB-name>/for_class_laptop/unpack_on_class_laptop.sh
#
# Puts everything in the same places as on the teaching laptop, then checks QGIS.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/Downloads" "$HOME/Desktop"

rsync -rt --info=progress2 "$HERE/sdn_datasets" "$HOME/Downloads/"
[ -d "$HERE/site_selection_v4" ] && rsync -rt --info=progress2 "$HERE/site_selection_v4" "$HOME/Desktop/"
chmod +x "$HOME/Downloads/sdn_datasets/sudan_site_analysis/"*.sh 2>/dev/null || true

echo
echo "== Checking QGIS for the scripts (/usr/bin/python3)"
/usr/bin/python3 - <<'PY'
import sys
try:
    from qgis.core import Qgis
    print("QGIS", Qgis.QGIS_VERSION, "| Python", sys.version.split()[0], "- OK")
except Exception as e:
    print("QGIS Python module not found:", e)
    print("Install with: sudo apt install python3-qgis")
PY

echo
echo "== Class QGIS history (for the class comparison)"
H="$HOME/.local/share/QGIS/QGIS3/profiles/default/history.db"
if [ -f "$H" ]; then
  mkdir -p "$HOME/Downloads/sdn_datasets/fromClass/qgis_history"
  cp "$H" "$HOME/Downloads/sdn_datasets/fromClass/qgis_history/"
  [ -f "${H%/history.db}/processing/processing.log" ] && cp "${H%/history.db}/processing/processing.log" "$HOME/Downloads/sdn_datasets/fromClass/qgis_history/"
  echo "Copied to ~/Downloads/sdn_datasets/fromClass/qgis_history/"
else
  echo "No history.db at $H"
fi

echo
echo "Done. Project: ~/Downloads/sdn_datasets/sudan_site_analysis"
echo "Run:  cd ~/Downloads/sdn_datasets/sudan_site_analysis && /usr/bin/python3 demo.py --only 3"
echo "Then open this chat in the Claude desktop app here and send a message."
