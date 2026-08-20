"""Shared visual constants for the hierarchy diagram."""

BOX_W = 170
BOX_H = 56  # baseline height used only for connector geometry; boxes themselves can grow taller
LINK_W = 40  # width of the horizontal bidirectional-arrow connector between parallel boxes
LINE_COLOR = "#7ea6e0"
LINK_COLOR = "#b98400"

HIER_CSS = f"""
<style>
.hier-row {{ display:flex; align-items:center; width:fit-content; margin:0 auto; }}
.hier-box {{ background:#eef4ff; border:1px solid {LINE_COLOR}; border-radius:8px;
            width:{BOX_W}px; min-height:{BOX_H}px; box-sizing:border-box; padding:6px 10px;
            text-align:center; display:flex; flex-direction:column; justify-content:center; }}
.hier-box-name {{ font-weight:600; font-size:0.85em; white-space:normal;
                  word-wrap:break-word; overflow-wrap:break-word; line-height:1.25em; }}
.hier-box-sub {{ font-size:0.72em; color:#4a5a75; margin-top:4px; }}
</style>
"""
