#!/bin/bash
# Converte gli SVG delle slide in PNG a doppia risoluzione (3200x1800). Serve rsvg-convert
# e i font IBM Plex (Ubuntu: apt install librsvg2-bin fonts-ibm-plex).
cd "$(dirname "$0")" && mkdir -p png
for f in svg/*.svg; do rsvg-convert -z 2 "$f" -o "png/$(basename "${f%.svg}").png"; done
ls -1 png
