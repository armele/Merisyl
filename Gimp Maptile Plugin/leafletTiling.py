import argparse
import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageFile
from tqdm import tqdm

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None

def calc_dimension(image):
    dimension = max(image.width, image.height)
    if dimension % 4096:
        dimension = int(dimension + (4096 - (dimension % 4096)))
    return dimension

def generate_tile(image, tile_x, tile_y, zoom, tile_size, output_format, output_dir, base_filename, crop_bounds, pbar_lock, pbar):
    width, height = image.size
    left = tile_x * tile_size
    upper = tile_y * tile_size
    right = min(left + tile_size, width)
    lower = min(upper + tile_size, height)

    if crop_bounds:
        crop_left, crop_upper, crop_right, crop_lower = crop_bounds
        tile_box_scaled = (left, upper, right, lower)
        intersects = not (
            tile_box_scaled[2] <= crop_left or tile_box_scaled[0] >= crop_right or
            tile_box_scaled[3] <= crop_upper or tile_box_scaled[1] >= crop_lower
        )
        if not intersects:
            with pbar_lock:
                pbar.update(1)
            return

    tile = image.crop((left, upper, right, lower))
    tile = tile.resize((tile_size, tile_size), resample=Image.Resampling.LANCZOS)

    tile_folder = os.path.join(output_dir, str(zoom), str(tile_x))
    os.makedirs(tile_folder, exist_ok=True)
    tile_filename = os.path.join(tile_folder, f"{tile_y}.{output_format}")
    tile.save(tile_filename, output_format.upper())

    with pbar_lock:
        pbar.update(1)

def main():
    parser = argparse.ArgumentParser(description="Tile generator for multi-zoom images.")
    parser.add_argument("image_path", help="Path to input image")
    parser.add_argument("max_zoom", type=int, help="Maximum zoom level to generate")
    parser.add_argument("--tile_size", type=int, default=256, help="Tile size in pixels (default: 256)")
    parser.add_argument("--webp", action="store_true", help="Save tiles in WebP format")
    parser.add_argument("--crop", nargs=4, type=int, metavar=('X_MIN', 'Y_MIN', 'X_MAX', 'Y_MAX'),
                        help="Only generate tiles intersecting this rectangle (in original image coordinates)")
    parser.add_argument("--threads", type=int, default=8, help="Number of worker threads to use (default: 8)")

    args = parser.parse_args()

    output_format = "webp" if args.webp else "png"
    base_filename = os.path.splitext(os.path.basename(args.image_path))[0]
    output_dir = f"tiles_{base_filename}_{output_format}"
    os.makedirs(output_dir, exist_ok=True)

    original_image = Image.open(args.image_path)
    dimension = calc_dimension(original_image)
    pad_x = (dimension - original_image.width) // 2
    pad_y = (dimension - original_image.height) // 2
    padded_image = Image.new("RGBA", (dimension, dimension), (255, 255, 255, 0))
    padded_image.paste(original_image, (pad_x, pad_y))

    pbar_lock = threading.Lock()

    for zoom_level in range(args.max_zoom, -1, -1):  # Leaflet: zoom 0 = most zoomed-out
        scale = 2 ** (args.max_zoom - zoom_level)
        zoom_width = math.ceil(dimension / scale)
        zoom_height = math.ceil(dimension / scale)

        if zoom_level == args.max_zoom:
            scaled_image = padded_image  # Use full resolution for max zoom
        else:
            scaled_image = padded_image.resize(
                (zoom_width, zoom_height), resample=Image.Resampling.LANCZOS
            )

        # Scale adjusted crop bounds per zoom level
        crop_bounds = None
        if args.crop:
            adjusted_crop = tuple(
                args.crop[i] + pad_x if i % 2 == 0 else args.crop[i] + pad_y for i in range(4)
            )
            crop_bounds = tuple(int(c / scale) for c in adjusted_crop)

        tiles_x = math.ceil(zoom_width / args.tile_size)
        tiles_y = math.ceil(zoom_height / args.tile_size)
        total_tiles = tiles_x * tiles_y

        with tqdm(total=total_tiles, desc=f"Zoom {zoom_level}", unit="tile") as pbar:
            with ThreadPoolExecutor(max_workers=args.threads) as executor:
                futures = []
                for x in range(tiles_x):
                    for y in range(tiles_y):
                        futures.append(executor.submit(
                            generate_tile, scaled_image, x, y, zoom_level, args.tile_size,
                            output_format, output_dir, base_filename,
                            crop_bounds, pbar_lock, pbar
                        ))
                for future in futures:
                    future.result()  # ensure exceptions are raised

if __name__ == "__main__":
    main()
