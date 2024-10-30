import json
import argparse
from svgpathtools import svg2paths
from shapely.geometry import Polygon, MultiPolygon

def svg_path_to_geojson(path_data, svg_size):
    """
    Convert an SVG path data to GeoJSON Polygon or MultiPolygon, adjusting coordinates to be relative to the image center.
    This assumes that the path represents a closed shape and the image is square.
    
    :param svg_size: The size of the SVG canvas (width and height, since it's square).
    """
    half_size = svg_size / 2  # Since the image is square, width = height
    polygons = []
    
    for path in path_data:
        coords = []
        for seg in path:
            # Adjust the coordinates to be centered around (0, 0) as the image center instead of the top-left corner
            centered_x = seg.start.real - half_size  # Translate X to center
            flipped_centered_y = half_size - seg.start.imag  # Flip Y and translate to center
            coords.append((centered_x, flipped_centered_y))  # Add adjusted (x, y) point

        # Creating a Polygon from path coordinates
        if coords:
            polygon = Polygon(coords)
            polygons.append(polygon)
    
    if len(polygons) > 1:
        return MultiPolygon(polygons).__geo_interface__
    elif len(polygons) == 1:
        return polygons[0].__geo_interface__
    else:
        return None

def svg_to_geojson(svg_file, geojson_file, svg_size):
    # Read paths from the SVG file
    paths, attributes = svg2paths(svg_file)
    
    # Convert each path to GeoJSON
    geojson_features = []
    for path in paths:
        geojson_geometry = svg_path_to_geojson([path], svg_size)
        if geojson_geometry:
            feature = {
                "type": "Feature",
                "geometry": geojson_geometry,
                "properties": {}
            }
            geojson_features.append(feature)

    # Create the final GeoJSON structure
    geojson = {
        "type": "FeatureCollection",
        "features": geojson_features
    }

    # Save the GeoJSON to a file
    with open(geojson_file, 'w') as f:
        json.dump(geojson, f, indent=2)

# Example Usage:
# python svgToGeoJSON.py .\locations\Aunea.svg -o ./locations/border.geojson --size 81920
if __name__ == "__main__":
    # Set up argument parsing
    parser = argparse.ArgumentParser(description='Convert SVG to GeoJSON with center-based coordinate transformation.')
    parser.add_argument('input_svg', type=str, help='Input SVG file')
    parser.add_argument('-o', '--output', type=str, default='output.geojson', help='Output GeoJSON file (default: output.geojson)')
    parser.add_argument('--size', type=float, required=True, help='Size of the square SVG canvas (width and height)')
    
    # Parse arguments
    args = parser.parse_args()

    # Run the conversion function
    svg_to_geojson(args.input_svg, args.output, args.size)
