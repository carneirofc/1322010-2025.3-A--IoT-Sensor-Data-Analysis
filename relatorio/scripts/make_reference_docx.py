#!/usr/bin/env python3
"""Generate template/docx/reference.docx: pandoc's default reference document
restyled for ABNT (stdlib only; needs `pandoc` on PATH).

  * A4, margins 3 cm (top/left) and 2 cm (bottom/right)
  * Times New Roman 12 pt, 1.5 line spacing, justified body, 1.25 cm indent
  * black headings: H1 bold caps, H2 bold, H3 regular — all 12 pt
  * captions 10 pt centered; cover/title-page/abstract custom styles used by
    template/filters/ufjf-front.lua (Capa, CapaEspaco, CapaTitulo, CapaRodape,
    Natureza, NaturezaOrientador, Resumo)

Usage: make_reference_docx.py [OUT] [--font "Times New Roman"]
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

CM = 567  # twips per cm


def style(sid: str, ppr: str, rpr: str = "", based: str = "Normal", kind: str = "paragraph", name: str | None = None) -> str:
    return (
        f'<w:style w:type="{kind}" w:customStyle="1" w:styleId="{sid}">'
        f'<w:name w:val="{name or sid}"/><w:basedOn w:val="{based}"/><w:qFormat/>'
        f"<w:pPr>{ppr}</w:pPr><w:rPr>{rpr}</w:rPr></w:style>"
    )


def replace_style(styles: str, sid: str, new: str) -> str:
    pat = re.compile(rf'<w:style\b[^>]*w:styleId="{sid}"[^>]*>.*?</w:style>', re.DOTALL)
    styles, n = pat.subn(lambda _m: new, styles, count=1)
    if n == 0:  # style absent in pandoc's default: append it
        styles = styles.replace("</w:styles>", new + "</w:styles>")
    return styles


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="template/docx/reference.docx", type=Path)
    ap.add_argument("--font", default="Times New Roman")
    a = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        default = Path(tmp) / "default.docx"
        subprocess.run(["pandoc", "-o", str(default), "--print-default-data-file", "reference.docx"], check=True)
        raw = default.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        items = {n: z.read(n) for n in z.namelist()}

    f = a.font
    fonts = f'<w:rFonts w:ascii="{f}" w:hAnsi="{f}" w:eastAsia="{f}" w:cs="{f}"/>'
    single = '<w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'
    onehalf = '<w:spacing w:before="0" w:after="0" w:line="360" w:lineRule="auto"/>'
    black = '<w:color w:val="000000"/>'
    sz = lambda hp: f'<w:sz w:val="{hp}"/><w:szCs w:val="{hp}"/>'  # half-points

    s = items["word/styles.xml"].decode("utf-8")

    # Defaults: font, size, spacing.
    s = re.sub(
        r"<w:docDefaults>.*?</w:docDefaults>",
        "<w:docDefaults><w:rPrDefault><w:rPr>" + fonts + sz(24) + '<w:lang w:val="pt-BR"/></w:rPr></w:rPrDefault>'
        "<w:pPrDefault><w:pPr>" + onehalf + "</w:pPr></w:pPrDefault></w:docDefaults>",
        s, count=1, flags=re.DOTALL,
    )

    body = '<w:spacing w:before="0" w:after="0" w:line="360" w:lineRule="auto"/><w:ind w:firstLine="709"/><w:jc w:val="both"/>'
    for sid, name in (("BodyText", "Body Text"), ("FirstParagraph", "First Paragraph")):
        s = replace_style(s, sid, style(sid, body, name=name))
    s = replace_style(s, "Compact", style("Compact", '<w:spacing w:before="36" w:after="36"/>', based="BodyText", name="Compact"))

    heads = {
        "Heading1": ("heading 1", "<w:b/><w:caps/>", 0),
        "Heading2": ("heading 2", "<w:b/>", 1),
        "Heading3": ("heading 3", "", 2),
        "Heading4": ("heading 4", "<w:i/>", 3),
    }
    for sid, (name, extra, lvl) in heads.items():
        new = (
            f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/>'
            '<w:basedOn w:val="Normal"/><w:next w:val="BodyText"/><w:uiPriority w:val="9"/><w:qFormat/>'
            f'<w:pPr><w:keepNext/><w:keepLines/><w:spacing w:before="360" w:after="240" w:line="360" w:lineRule="auto"/>'
            f'<w:outlineLvl w:val="{lvl}"/></w:pPr><w:rPr>{fonts}{extra}{black}{sz(24)}</w:rPr></w:style>'
        )
        s = replace_style(s, sid, new)

    cap = '<w:spacing w:before="120" w:after="240" w:line="240" w:lineRule="auto"/><w:jc w:val="center"/>'
    for sid, name in (("ImageCaption", "Image Caption"), ("TableCaption", "Table Caption"), ("Caption", "caption")):
        s = replace_style(s, sid, style(sid, cap, black + sz(20), name=name))
    s = replace_style(s, "TOCHeading", style("TOCHeading", '<w:jc w:val="center"/><w:spacing w:before="0" w:after="240"/>', "<w:b/>" + black + sz(24), based="Heading1", name="TOC Heading"))

    center = '<w:jc w:val="center"/>'
    covers = {
        "Capa": (f'<w:spacing w:before="80" w:after="80" w:line="240" w:lineRule="auto"/>{center}', ""),
        "CapaEspaco": (f'<w:spacing w:before="2600" w:after="80" w:line="240" w:lineRule="auto"/>{center}', ""),
        "CapaTitulo": (f'<w:spacing w:before="2600" w:after="120" w:line="240" w:lineRule="auto"/>{center}', sz(28)),
        "CapaRodape": (f'<w:spacing w:before="2600" w:after="80" w:line="240" w:lineRule="auto"/>{center}', ""),
        "Natureza": (f'<w:spacing w:before="1400" w:after="80" w:line="240" w:lineRule="auto"/><w:ind w:left="{8 * CM}"/><w:jc w:val="both"/>', ""),
        "NaturezaOrientador": (f'<w:spacing w:before="480" w:after="80" w:line="240" w:lineRule="auto"/><w:ind w:left="{8 * CM}"/>', ""),
        "Resumo": (f'{single}<w:spacing w:before="0" w:after="240" w:line="240" w:lineRule="auto"/><w:jc w:val="both"/>', ""),
    }
    for sid, (ppr, rpr) in covers.items():
        s = replace_style(s, sid, style(sid, ppr, rpr))

    # Theme fonts would otherwise override Normal for some styles.
    s = re.sub(r'<w:rFonts [^>]*Theme[^>]*/>', fonts, s)
    items["word/styles.xml"] = s.encode("utf-8")

    # Page: A4 + ABNT margins.
    d = items["word/document.xml"].decode("utf-8")
    sect = (
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        f'<w:pgMar w:top="{3 * CM}" w:right="{2 * CM}" w:bottom="{2 * CM}" w:left="{3 * CM}" '
        'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
    )
    d, n = re.subn(r"<w:sectPr\b.*?</w:sectPr>|<w:sectPr\s*/>", sect, d, flags=re.DOTALL)
    if n == 0:
        d = d.replace("</w:body>", sect + "</w:body>")
    items["word/document.xml"] = d.encode("utf-8")

    a.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as out:
        for name, data in items.items():
            out.writestr(name, data)
    print(f"ok -> {a.out}")


if __name__ == "__main__":
    main()
