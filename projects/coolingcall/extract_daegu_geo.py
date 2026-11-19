"""2018 행정동 경계(topojson, 통계청 기준)에서 대구광역시 행정동만 잘라 GeoJSON으로 저장한다.

- 입력: data/geo/sub2018_topo_simple.json (공개 저장소 southkorea-maps, 통계청 2018 기준 경계)
- 출력: data/geo/daegu_dongs.geojson (features: name, code, gu, geometry)
- topojson arcs의 delta 인코딩을 직접 디코드한다(외부 라이브러리 미사용).
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "data" / "geo" / "sub2018_topo_simple.json"
OUT = HERE / "data" / "geo" / "daegu_dongs.geojson"

# 통계청 2018 기준 코드체계에서 대구광역시는 22로 시작한다(현행 27과 다름).
GU = {
    "22010": "중구",
    "22020": "동구",
    "22030": "서구",
    "22040": "남구",
    "22050": "북구",
    "22060": "수성구",
    "22070": "달서구",
    "22310": "달성군",
}


def decode_arcs(topo):
    tr = topo["transform"]
    sx, sy = tr["scale"]
    tx, ty = tr["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)
    return arcs


def ring(coords, arcs):
    out = []
    for idx in coords:
        if idx >= 0:
            pts = arcs[idx]
        else:
            pts = list(reversed(arcs[~idx]))
        if out:
            out.extend(pts[1:])
        else:
            out.extend(pts)
    return out


def main() -> None:
    topo = json.loads(SRC.read_text(encoding="utf-8"))
    arcs = decode_arcs(topo)
    obj = list(topo["objects"].values())[0]
    feats = []
    for g in obj["geometries"]:
        code = g["properties"]["code"]
        if not str(code).startswith("22"):
            continue
        geom = g["geometry"] if "geometry" in g else g
        typ = g["type"]
        if typ == "Polygon":
            polys = [ring(r, arcs) for r in g["arcs"]]
        elif typ == "MultiPolygon":
            polys = [[ring(r, arcs) for r in poly] for poly in g["arcs"]]
        else:
            continue
        geojson_geom = {
            "type": typ,
            "coordinates": polys,
        }
        feats.append(
            {
                "type": "Feature",
                "properties": {
                    "name": g["properties"]["name"],
                    "code": str(code),
                    "gu": GU.get(str(code)[:5], ""),
                },
                "geometry": geojson_geom,
            }
        )
    OUT.write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False),
        encoding="utf-8",
    )
    print("features:", len(feats), "->", OUT)


if __name__ == "__main__":
    main()
