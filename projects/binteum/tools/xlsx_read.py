"""Minimal stdlib-only xlsx reader (for schema inspection of the DAKER sample workbook)."""
import sys
import zipfile
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def sheet_map(path):
    z = zipfile.ZipFile(path)
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rel = {r.get("Id"): r.get("Target") for r in rels}
    out = []
    for s in wb.find("m:sheets", NS):
        out.append((s.get("name"), rel[s.get(R + "id")]))
    return z, out


def rows(path, size=200):
    z, sheets = sheet_map(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        ss = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in ss:
            shared.append("".join(t.text or "" for t in si.iter(M + "t")))
    for name, target in sheets:
        p = target.lstrip("/")
        if p not in z.namelist():
            p = "xl/" + p
        try:
            root = ET.fromstring(z.read(p))
        except Exception as exc:  # pragma: no cover
            print("ERR", name, exc)
            continue
        data = []
        for row in root.iter(M + "row"):
            vals = []
            for c in row:
                t = c.get("t")
                if t == "inlineStr":
                    vals.append("".join(x.text or "" for x in c.iter(M + "t")))
                    continue
                v = c.find("m:v", NS)
                if v is None:
                    vals.append("")
                elif t == "s":
                    vals.append(shared[int(v.text)])
                else:
                    vals.append(v.text)
            data.append(vals)
            if len(data) >= size:
                break
        yield name, data


if __name__ == "__main__":
    path = sys.argv[1]
    want = sys.argv[2] if len(sys.argv) > 2 else ""
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    for name, data in rows(path):
        if want and want not in name:
            continue
        print("=== SHEET:", name, len(data), "rows")
        for r in data[:n]:
            print(" | ".join(str(x)[:60] for x in r))
