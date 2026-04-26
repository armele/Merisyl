import argparse
import gc
import logging
import math
import os
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from PIL import Image, ImageFile
from tqdm import tqdm

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None

BYTES_PER_RGBA_PIXEL = 4


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )


def calc_dimension(width: int, height: int, multiple: int = 4096) -> int:
    dimension = max(width, height)
    if dimension % multiple:
        dimension += multiple - (dimension % multiple)
    return int(dimension)


def human_bytes(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"


def get_available_memory_bytes() -> int | None:
    """Best-effort available memory check. Uses psutil when installed; otherwise returns None."""
    try:
        import psutil  # type: ignore

        return int(psutil.virtual_memory().available)
    except Exception:
        return None


def estimate_image_bytes(width: int, height: int) -> int:
    return width * height * BYTES_PER_RGBA_PIXEL


def choose_thread_count(requested_threads: int, tile_size: int, memory_limit_gb: float | None) -> int:
    """
    Keep the tile worker pool bounded. Each worker may briefly hold cropped/resized/encoded tile data.
    This is intentionally conservative; image-wide memory is handled separately by processing one zoom at a time.
    """
    requested_threads = max(1, requested_threads)
    per_worker_estimate = tile_size * tile_size * BYTES_PER_RGBA_PIXEL * 8

    available = get_available_memory_bytes()
    if memory_limit_gb is not None:
        available = int(memory_limit_gb * 1024**3) if available is None else min(available, int(memory_limit_gb * 1024**3))

    if available is None:
        return requested_threads

    # Reserve most RAM for the currently loaded zoom image and the OS.
    worker_budget = max(64 * 1024**2, int(available * 0.10))
    memory_based_threads = max(1, worker_budget // max(1, per_worker_estimate))
    return max(1, min(requested_threads, int(memory_based_threads)))


def make_padded_image(original_image: Image.Image, max_dimension: int) -> tuple[Image.Image, float, tuple[int, int]]:
    original_width, original_height = original_image.size

    if original_width >= original_height:
        scale_factor = max_dimension / original_width
        new_width = max_dimension
        new_height = int(original_height * scale_factor)
        logging.info("Resizing source to %s x %s before vertical padding", new_width, new_height)
        scaled_image = original_image.resize((new_width, new_height), resample=Image.Resampling.LANCZOS).convert("RGBA")
        pad_left, pad_top = 0, (max_dimension - new_height) // 2
    else:
        scale_factor = max_dimension / original_height
        new_height = max_dimension
        new_width = int(original_width * scale_factor)
        logging.info("Resizing source to %s x %s before horizontal padding", new_width, new_height)
        scaled_image = original_image.resize((new_width, new_height), resample=Image.Resampling.LANCZOS).convert("RGBA")
        pad_left, pad_top = (max_dimension - new_width) // 2, 0

    logging.info("Creating padded square canvas: %s x %s", max_dimension, max_dimension)
    padded_image = Image.new("RGBA", (max_dimension, max_dimension), (255, 255, 255, 0))
    padded_image.paste(scaled_image, (pad_left, pad_top))
    scaled_image.close()
    return padded_image, scale_factor, (pad_left, pad_top)


def scaled_crop_bounds(
    crop: list[int] | None,
    scale_factor: float,
    pad_offset: tuple[int, int],
    zoom_scale: int,
) -> tuple[int, int, int, int] | None:
    if not crop:
        return None

    pad_left, pad_top = pad_offset
    x_min, y_min, x_max, y_max = crop
    adjusted = (
        int(x_min * scale_factor) + pad_left,
        int(y_min * scale_factor) + pad_top,
        int(x_max * scale_factor) + pad_left,
        int(y_max * scale_factor) + pad_top,
    )
    return tuple(int(c / zoom_scale) for c in adjusted)


def tile_intersects_crop(tile_box: tuple[int, int, int, int], crop_bounds: tuple[int, int, int, int] | None) -> bool:
    if crop_bounds is None:
        return True
    left, upper, right, lower = tile_box
    crop_left, crop_upper, crop_right, crop_lower = crop_bounds
    return not (right <= crop_left or left >= crop_right or lower <= crop_upper or upper >= crop_lower)


def generate_tile(
    image: Image.Image,
    tile_x: int,
    tile_y: int,
    zoom: int,
    tile_size: int,
    output_format: str,
    output_dir: Path,
    crop_bounds: tuple[int, int, int, int] | None,
    skip_existing: bool,
) -> str:
    width, height = image.size
    left = tile_x * tile_size
    upper = tile_y * tile_size
    right = min(left + tile_size, width)
    lower = min(upper + tile_size, height)

    tile_folder = output_dir / str(zoom) / str(tile_x)
    tile_filename = tile_folder / f"{tile_y}.{output_format}"

    if skip_existing and tile_filename.exists():
        return "skipped-existing"

    if not tile_intersects_crop((left, upper, right, lower), crop_bounds):
        return "skipped-crop"

    tile_folder.mkdir(parents=True, exist_ok=True)

    with image.crop((left, upper, right, lower)) as tile:
        if tile.size != (tile_size, tile_size):
            tile = tile.resize((tile_size, tile_size), resample=Image.Resampling.LANCZOS)
        tile.save(tile_filename, output_format.upper())

    return "written"


def bounded_tile_generation(
    *,
    zoom_image: Image.Image,
    zoom_level: int,
    tiles_x: int,
    tiles_y: int,
    tile_size: int,
    output_format: str,
    output_dir: Path,
    crop_bounds: tuple[int, int, int, int] | None,
    max_workers: int,
    max_pending: int,
    skip_existing: bool,
) -> dict[str, int]:
    stats = {"written": 0, "skipped-crop": 0, "skipped-existing": 0}
    pending = set()

    def drain_completed(block: bool) -> None:
        nonlocal pending
        if not pending:
            return
        done, pending = wait(pending, return_when=FIRST_COMPLETED if block else FIRST_COMPLETED)
        for future in done:
            stats[future.result()] += 1

    total_tiles = tiles_x * tiles_y
    with tqdm(total=total_tiles, desc=f"Zoom {zoom_level}", unit="tile") as pbar:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            last_update = time.monotonic()
            for x in range(tiles_x):
                for y in range(tiles_y):
                    while len(pending) >= max_pending:
                        before = sum(stats.values())
                        drain_completed(block=True)
                        pbar.update(sum(stats.values()) - before)

                    pending.add(
                        executor.submit(
                            generate_tile,
                            zoom_image,
                            x,
                            y,
                            zoom_level,
                            tile_size,
                            output_format,
                            output_dir,
                            crop_bounds,
                            skip_existing,
                        )
                    )

                    now = time.monotonic()
                    if now - last_update >= 10:
                        logging.info(
                            "Zoom %s progress: %s/%s complete; %s tasks pending",
                            zoom_level,
                            sum(stats.values()),
                            total_tiles,
                            len(pending),
                        )
                        last_update = now

            while pending:
                before = sum(stats.values())
                drain_completed(block=True)
                pbar.update(sum(stats.values()) - before)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory-aware tile generator for Leaflet multi-zoom images.")
    parser.add_argument("image_path", help="Path to input image")
    parser.add_argument("max_zoom", type=int, help="Maximum zoom level to generate")
    parser.add_argument("--tile_size", type=int, default=256, help="Tile size in pixels (default: 256)")
    parser.add_argument("--webp", action="store_true", help="Save tiles in WebP format")
    parser.add_argument("--crop", nargs=4, type=int, metavar=("X_MIN", "Y_MIN", "X_MAX", "Y_MAX"), help="Only generate tiles intersecting this rectangle, in original image coordinates")
    parser.add_argument("--threads", type=int, default=8, help="Maximum worker threads to use (default: 8)")
    parser.add_argument("--max_pending", type=int, default=24, help="Maximum queued tile tasks. Default: threads * 4")
    parser.add_argument("--memory_limit_gb", type=float, default=48, help="Optional soft memory budget used to cap worker threads")
    parser.add_argument("--skip_existing", action="store_true", help="Do not regenerate existing tile files")
    parser.add_argument("--no_reference", action="store_true", help="Do not save the full max-zoom reference image")
    parser.add_argument("--verbose", action="store_true", help="Show more detailed status messages")
    args = parser.parse_args()

    configure_logging(args.verbose)

    image_path = Path(args.image_path)
    output_format = "webp" if args.webp else "png"
    base_filename = image_path.stem
    output_dir = Path(f"tiles_{base_filename}_{output_format}")
    output_dir.mkdir(parents=True, exist_ok=True)

    logging.info("Opening source image: %s", image_path)
    with Image.open(image_path) as original_image:
        original_width, original_height = original_image.size
        max_dimension = calc_dimension(original_width, original_height)
        logging.info("Source dimensions: %s x %s", original_width, original_height)
        logging.info("Padded map dimension: %s x %s", max_dimension, max_dimension)
        logging.info("Estimated padded image memory: %s", human_bytes(estimate_image_bytes(max_dimension, max_dimension)))

        available = get_available_memory_bytes()
        if available is not None:
            logging.info("Approximate available system memory: %s", human_bytes(available))

        padded_image, scale_factor, pad_offset = make_padded_image(original_image, max_dimension)

    if not args.no_reference:
        reference_path = output_dir / f"{base_filename}_maxzoom.{output_format}"
        logging.info("Saving max-zoom reference image: %s", reference_path)
        padded_image.save(reference_path, output_format.upper())

    worker_count = choose_thread_count(args.threads, args.tile_size, args.memory_limit_gb)
    max_pending = args.max_pending or worker_count * 4
    max_pending = max(worker_count, max_pending)
    logging.info("Using %s worker thread(s), with at most %s queued tile task(s)", worker_count, max_pending)

    grand_total = {"written": 0, "skipped-crop": 0, "skipped-existing": 0}

    for zoom_level in range(args.max_zoom, -1, -1):
        zoom_scale = 2 ** (args.max_zoom - zoom_level)
        zoom_width = math.ceil(max_dimension / zoom_scale)
        zoom_height = math.ceil(max_dimension / zoom_scale)

        logging.info("Preparing zoom %s: %s x %s", zoom_level, zoom_width, zoom_height)
        if zoom_level == args.max_zoom:
            zoom_image = padded_image
        else:
            zoom_image = padded_image.resize((zoom_width, zoom_height), resample=Image.Resampling.LANCZOS)

        crop_bounds = scaled_crop_bounds(args.crop, scale_factor, pad_offset, zoom_scale)
        if crop_bounds:
            logging.info("Zoom %s crop bounds after scaling/padding: %s", zoom_level, crop_bounds)

        tiles_x = math.ceil(zoom_width / args.tile_size)
        tiles_y = math.ceil(zoom_height / args.tile_size)
        logging.info("Generating zoom %s tiles: %s columns x %s rows = %s tiles", zoom_level, tiles_x, tiles_y, tiles_x * tiles_y)

        stats = bounded_tile_generation(
            zoom_image=zoom_image,
            zoom_level=zoom_level,
            tiles_x=tiles_x,
            tiles_y=tiles_y,
            tile_size=args.tile_size,
            output_format=output_format,
            output_dir=output_dir,
            crop_bounds=crop_bounds,
            max_workers=worker_count,
            max_pending=max_pending,
            skip_existing=args.skip_existing,
        )

        for key, value in stats.items():
            grand_total[key] += value
        logging.info("Finished zoom %s: %s", zoom_level, stats)

        if zoom_image is not padded_image:
            zoom_image.close()
        gc.collect()

    padded_image.close()
    logging.info("Done. Output directory: %s", output_dir)
    logging.info("Final tile summary: %s", grand_total)


if __name__ == "__main__":
    main()
