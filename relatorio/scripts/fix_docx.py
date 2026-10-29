#!/usr/bin/env python3
"""Post-process the pandoc DOCX into ABNT order (stdlib only).

  1. Move the table of contents (the <w:sdt> pandoc puts at the very top)
     after the pretextual pages, right before the first Heading 1.
  2. Ask Word/LibreOffice to refresh fields on open (repaginates the TOC).
  3. Fill docProps title/creator, which pandoc leaves empty because the
     template keeps its metadata under `report:`.

Usage: fix_docx.py FILE.docx [--title T] [--author A]
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

PAGE_BREAK = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("docx", type=Path)
    ap.add_argument("--title", default="")
    ap.add_argument("--author", default="")
    args = ap.parse_args()

    with zipfile.ZipFile(args.docx) as z:
        items = {n: z.read(n) for n in z.namelist()}

    doc = items["word/document.xml"].decode("utf-8")
    settings = items["word/settings.xml"].decode("utf-8")

    # 1. Relocate the TOC.
    toc = re.search(r"<w:sdt>.*?</w:sdt>", doc, re.DOTALL)
    heading = re.search(r'<w:pStyle w:val="Heading1"\s*/>', doc)
    if toc and heading and toc.start() < heading.start():
        block = toc.group(0)
        doc = doc[: toc.start()] + doc[toc.end():]
        heading = re.search(r'<w:pStyle w:val="Heading1"\s*/>', doc)
        p_start = doc.rfind("<w:p>", 0, heading.start())
        p_start2 = doc.rfind("<w:p ", 0, heading.start())
        p_start = max(p_start, p_start2)
        doc = doc[:p_start] + block + PAGE_BREAK + doc[p_start:]
    else:
        print("fix_docx: TOC or first Heading 1 not found; TOC left in place", file=sys.stderr)

    # 2. Refresh fields on open.
    if "<w:updateFields" not in settings:
        settings = re.sub(r"(<w:settings\b[^>]*>)", r'\1<w:updateFields w:val="true"/>', settings, count=1)

    # 3. Core properties.
    core = items["docProps/core.xml"].decode("utf-8")
    for tag, value in (("dc:title", args.title), ("dc:creator", args.author)):
        if not value:
            continue
        new = f"<{tag}>{escape(value)}</{tag}>"
        core, n = re.subn(rf"<{tag}\s*/>|<{tag}>.*?</{tag}>", new, core, count=1, flags=re.DOTALL)
        if n == 0:
            core = core.replace("</cp:coreProperties>", new + "</cp:coreProperties>")

    items["word/document.xml"] = doc.encode("utf-8")
    items["word/settings.xml"] = settings.encode("utf-8")
    items["docProps/core.xml"] = core.encode("utf-8")

    tmp = args.docx.with_suffix(".tmp.docx")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
        for name, data in items.items():
            out.writestr(name, data)
    shutil.move(str(tmp), str(args.docx))
    print(f"fix_docx: ok -> {args.docx}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
