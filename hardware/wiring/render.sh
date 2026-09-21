#!/bin/sh
# Renders every numbered .yml here into ../images/ as PNG.
#
# One drawing per run of wire, small enough to read at page width. WireViz lays
# a harness out left to right, which is wide and short; we take its Graphviz
# source, turn the layout top to bottom and run dot ourselves.
#
# Needs: wireviz (pip) and graphviz (dot).
set -e
cd "$(dirname "$0")"

for yml in [0-9]-*.yml; do
  name="${yml%.yml}"
  wireviz -p _common.yml -f g "$yml" >/dev/null
  sed 's/rankdir=LR ranksep=2/rankdir=TB ranksep=0.5 nodesep=0.3/' "$name.gv" > "$name.tb.gv"
  dot -Tpng -o "../images/$name.png" "$name.tb.gv"
  rm -f "$name.gv" "$name.tb.gv"
  echo "$name -> ../images/$name.png"
done
