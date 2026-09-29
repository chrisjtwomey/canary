# The wiring diagrams

This folder holds the circuit as YAML, one file for each run of wire. [WireViz](https://github.com/wireviz/WireViz)
makes the drawings in `hardware/images/` from it. Edit the YAML, never the PNG.

```sh
pip install wireviz          # and graphviz: brew install graphviz
hardware/wiring/render.sh    # writes the drawings in hardware/images/ again
```

- `render.sh` turns WireViz's layout top to bottom, and runs `dot` itself. WireViz's own left-to-right layout is too
  wide and too short to read on a page.
- **Keep each drawing near 1200 px.** That size stays legible at page width. One run of wire per file does this. Do
  not draw a chain of identical cables: say it in a sentence.
- **Give every wire a colour, and never `WH`.** A white line on a white page looks like no wire. Red is a supply,
  black is ground, blue is SDA and yellow is SCL. For other wires, use a colour that stands out.
- [assembly.md](../assembly.md) lists the same joints, under "Appendix: every joint". When you change one, change
  the other.
