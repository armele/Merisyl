import json
import sys
from PIL import Image

# Load configuration file
def load_config(config_path):
    with open(config_path, 'r') as file:
        return json.load(file)

# Calculate offsets based on anchor points
def calculate_offsets(anchor_points):
    base_anchor = anchor_points['quadrant1']  # Use the first quadrant's anchor as reference
    offsets = {}
    for quadrant, point in anchor_points.items():
        offsets[quadrant] = (base_anchor[0] - point[0], base_anchor[1] - point[1])
    return offsets

# Combine images
def combine_images(images, offsets):
    # Determine canvas size
    min_x, min_y, max_x, max_y = 0, 0, 0, 0

    for i, image in enumerate(images):
        quadrant = f'quadrant{i+1}'
        offset = offsets[quadrant]
        min_x = min(min_x, offset[0])
        min_y = min(min_y, offset[1])
        max_x = max(max_x, offset[0] + image.width)
        max_y = max(max_y, offset[1] + image.height)

    canvas_width = max_x - min_x
    canvas_height = max_y - min_y

    # Create blank canvas
    canvas = Image.new("RGBA", (canvas_width, canvas_height))

    # Paste each image onto the canvas
    for i, image in enumerate(images):
        quadrant = f'quadrant{i+1}'
        offset = offsets[quadrant]
        canvas.paste(image, (offset[0] - min_x, offset[1] - min_y))

    return canvas

# Main function
def main(config_path):
    # Load config
    config = load_config(config_path)

    # Load images
    images = [Image.open(config['images'][f'quadrant{i+1}']) for i in range(4)]

    # Calculate offsets
    offsets = calculate_offsets(config['anchor_points'])

    # Combine images
    combined_image = combine_images(images, offsets)

    # Save the result
    combined_image.save(config['output'])
    print(f"Combined image saved to {config['output']}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python combine_quadrants.py <config_path>")
        sys.exit(1)

    config_path = sys.argv[1]
    main(config_path)
