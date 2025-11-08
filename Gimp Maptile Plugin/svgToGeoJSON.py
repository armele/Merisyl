import json
import argparse
from svgpathtools import svg2paths
from shapely.geometry import Polygon, MultiPolygon

def svg_path_to_geojson(path_data, svg_size, offset_x=0.0, offset_y=0.0):
    """
    Convert SVG path data to GeoJSON Polygon or MultiPolygon, adjusting coordinates
    to be relative to the image center and applying an optional translation.

    Coordinate system (output):
      - (0, 0) at the center of the SVG
      - +X to the right (east)
      - +Y up (north)
      - To move shapes south (down), use a NEGATIVE offset_y.

    :param path_data: Iterable of svgpathtools Path objects.
    :param svg_size: Size of the square SVG canvas (width == height).
    :param offset_x: Translation in X applied AFTER centering.
    :param offset_y: Translation in Y applied AFTER centering.
    """
    half_size = svg_size / 2.0
    polygons = []

    for path in path_data:
        coords = []
        for seg in path:
            # Base centered coordinates
            centered_x = seg.start.real - half_size
            flipped_centered_y = half_size - seg.start.imag  # flip Y, then center

            # Apply translation offsets
            x = centered_x + offset_x
            y = flipped_centered_y + offset_y

            coords.append((x, y))

        if coords:
            polygon = Polygon(coords)
            if not polygon.is_empty:
                polygons.append(polygon)

    if len(polygons) > 1:
        return MultiPolygon(polygons).__geo_interface__
    elif len(polygons) == 1:
        return polygons[0].__geo_interface__
    else:
        return None

def svg_to_geojson(svg_file, geojson_file, svg_size, offset_x=0.0, offset_y=0.0):
    # Read paths from the SVG file
    paths, attributes = svg2paths(svg_file)

    geojson_features = []
    for path in paths:
        geojson_geometry = svg_path_to_geojson([path], svg_size, offset_x, offset_y)
        if geojson_geometry:
            feature = {
                "type": "Feature",
                "geometry": geojson_geometry,
                "properties": {}
            }
            geojson_features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "features": geojson_features
    }

    with open(geojson_file, 'w') as f:
        json.dump(geojson, f, indent=2)

# Example Usage:
# python svgToGeoJSON.py .\locations\Aunea.svg -o .\locations\Aunea.geojson --size 81920 --offset-y -250 --offset-x +85
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Convert SVG to GeoJSON with center-based coordinates and optional translation.'
    )
    parser.add_argument('input_svg', type=str, help='Input SVG file')
    parser.add_argument(
        '-o', '--output',
        type=str,
        default='output.geojson',
        help='Output GeoJSON file (default: output.geojson)'
    )
    parser.add_argument(
        '--size',
        type=float,
        required=True,
        help='Size of the square SVG canvas (width and height)'
    )
    parser.add_argument(
        '--offset-x',
        type=float,
        default=0.0,
        help='Horizontal offset AFTER centering (positive = east/right)'
    )
    parser.add_argument(
        '--offset-y',
        type=float,
        default=0.0,
        help='Vertical offset AFTER centering (positive = north/up, negative = south/down)'
    )

    args = parser.parse_args()

    svg_to_geojson(
        args.input_svg,
        args.output,
        args.size,
        offset_x=args.offset_x,
        offset_y=args.offset_y
    )
