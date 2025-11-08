import json
import argparse


def offset_coords(coords, dx, dy):
    """Offset a single [x, y] or [x, y, ...] coordinate."""
    if len(coords) >= 2:
        return [coords[0] + dx, coords[1] + dy, *coords[2:]]
    return coords


def offset_geometry(geometry, dx, dy):
    """
    Recursively offset coordinates in a GeoJSON geometry.
    Supports:
      Point, MultiPoint, LineString, MultiLineString,
      Polygon, MultiPolygon, GeometryCollection.
    """
    if geometry is None:
        return None

    gtype = geometry.get("type")

    if gtype == "Point":
        geometry["coordinates"] = offset_coords(geometry["coordinates"], dx, dy)

    elif gtype == "MultiPoint":
        geometry["coordinates"] = [
            offset_coords(coord, dx, dy) for coord in geometry["coordinates"]
        ]

    elif gtype == "LineString":
        geometry["coordinates"] = [
            offset_coords(coord, dx, dy) for coord in geometry["coordinates"]
        ]

    elif gtype == "MultiLineString":
        geometry["coordinates"] = [
            [offset_coords(coord, dx, dy) for coord in line]
            for line in geometry["coordinates"]
        ]

    elif gtype == "Polygon":
        # List of linear rings: [ [ [x,y], ... ], [hole], ... ]
        geometry["coordinates"] = [
            [offset_coords(coord, dx, dy) for coord in ring]
            for ring in geometry["coordinates"]
        ]

    elif gtype == "MultiPolygon":
        # List of polygons, each polygon is list of linear rings
        geometry["coordinates"] = [
            [
                [offset_coords(coord, dx, dy) for coord in ring]
                for ring in polygon
            ]
            for polygon in geometry["coordinates"]
        ]

    elif gtype == "GeometryCollection":
        geometry["geometries"] = [
            offset_geometry(geom, dx, dy) for geom in geometry.get("geometries", [])
        ]

    else:
        # Unknown type; leave as-is
        pass

    return geometry


def offset_feature(feature, dx, dy):
    """Offset the geometry of a single Feature."""
    if feature.get("type") != "Feature":
        return feature

    geom = feature.get("geometry")
    if geom:
        feature["geometry"] = offset_geometry(geom, dx, dy)
    return feature


def offset_geojson(data, dx, dy):
    """
    Apply an offset to all geometries in a GeoJSON object.
    Handles:
      - FeatureCollection
      - Feature
      - Geometry (any supported type)
    """
    dtype = data.get("type")

    if dtype == "FeatureCollection":
        data["features"] = [
            offset_feature(f, dx, dy) for f in data.get("features", [])
        ]

    elif dtype == "Feature":
        data = offset_feature(data, dx, dy)

    else:
        # Assume it's a bare geometry object
        data = offset_geometry(data, dx, dy)

    return data


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Offset all coordinates in a GeoJSON file by a specified amount.\n\n"
            "Note: Offsets are applied directly to the stored coordinates.\n"
            "For data from the SVG-center script:\n"
            "  +offset-x = east/right\n"
            "  +offset-y = north/up\n"
            "To move shapes south/down by 250 units, use: --offset-y -250"
        ),
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument("input_geojson", help="Input GeoJSON file")
    parser.add_argument(
        "-o", "--output",
        default="offset.geojson",
        help="Output GeoJSON file (default: offset.geojson)"
    )
    parser.add_argument(
        "--offset-x",
        type=float,
        default=0.0,
        help="Offset to add to all X coordinates (default: 0.0)"
    )
    parser.add_argument(
        "--offset-y",
        type=float,
        default=0.0,
        help="Offset to add to all Y coordinates (default: 0.0)"
    )

    args = parser.parse_args()

    with open(args.input_geojson, "r") as f:
        data = json.load(f)

    shifted = offset_geojson(data, args.offset_x, args.offset_y)

    with open(args.output, "w") as f:
        json.dump(shifted, f, indent=2)

if __name__ == "__main__":
    main()
