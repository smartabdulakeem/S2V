"""
pipeline/magick_processor.py

Pillow-based image processing for S2V filters and grades.
Replaces ImageMagick subprocess calls with pure Python / Pillow / numpy operations.
"""

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import numpy as np


def _crop_cover(img: Image.Image, width: int, height: int) -> Image.Image:
    target_ratio = width / height
    current_w, current_h = img.size
    current_ratio = current_w / current_h

    if current_ratio > target_ratio:
        new_w = int(target_ratio * current_h)
        left = (current_w - new_w) // 2
        img = img.crop((left, 0, left + new_w, current_h))
    elif current_ratio < target_ratio:
        new_h = int(current_w / target_ratio)
        top = (current_h - new_h) // 2
        img = img.crop((0, top, current_w, top + new_h))

    return img.resize((width, height), Image.Resampling.LANCZOS)


def _apply_radial_vignette(img: Image.Image, strength: float = 0.6, inner_radius: float = 0.35, outer_radius: float = 1.2) -> Image.Image:
    w, h = img.size
    x = np.linspace(-1, 1, w)
    y = np.linspace(-1, 1, h)
    xx, yy = np.meshgrid(x, y)
    radius = np.sqrt(xx**2 + yy**2)

    falloff = np.clip((radius - inner_radius) / (outer_radius - inner_radius), 0, 1) ** 2
    vignette = 1 - falloff * strength
    vignette = np.stack([vignette] * 3, axis=-1)

    img_np = np.array(img.convert("RGB"), dtype=np.float32)
    vignetted = np.clip(img_np * vignette, 0, 255).astype(np.uint8)
    return Image.fromarray(vignetted)


def _apply_gaussian_grain(img: Image.Image, sigma: float = 6.0) -> Image.Image:
    w, h = img.size
    noise = np.random.normal(0, sigma, (h, w, 3))
    img_np = np.array(img.convert("RGB"), dtype=np.float32) + noise
    return Image.fromarray(np.clip(img_np, 0, 255).astype(np.uint8))


def process_vignette(input_path: str, output_path: str, width: int = 1280, height: int = 720):
    img = Image.open(input_path).convert("RGB")
    img = _crop_cover(img, width, height)
    img = _apply_radial_vignette(img, strength=0.6)
    img = _apply_gaussian_grain(img, sigma=5.0)
    img.save(output_path, "JPEG", quality=95)


def process_diptych(img1_path: str, img2_path: str, output_path: str, width: int = 1280, height: int = 720):
    half_w = width // 2
    img1 = Image.open(img1_path).convert("RGB")
    img2 = Image.open(img2_path).convert("RGB")

    crop1 = _crop_cover(img1, half_w, height)
    crop2 = _crop_cover(img2, width - half_w, height)

    canvas = Image.new("RGB", (width, height))
    canvas.paste(crop1, (0, 0))
    canvas.paste(crop2, (half_w, 0))

    canvas = _apply_radial_vignette(canvas, strength=0.5)
    canvas = _apply_gaussian_grain(canvas, sigma=4.0)
    canvas.save(output_path, "JPEG", quality=95)


def process_collage(img1_path: str, img2_path: str, output_path: str, width: int = 1280, height: int = 720):
    half_w = width // 2
    img1 = Image.open(img1_path).convert("RGB")
    img2 = Image.open(img2_path).convert("RGB")

    crop1 = _crop_cover(img1, half_w, height)
    crop2 = _crop_cover(img2, width - half_w, height)

    canvas = Image.new("RGB", (width, height))
    canvas.paste(crop1, (0, 0))
    canvas.paste(crop2, (half_w, 0))

    canvas = _apply_radial_vignette(canvas, strength=0.5)
    canvas.save(output_path, "JPEG", quality=95)


def process_vox_collage(input_path: str, output_path: str, width: int = 1280, height: int = 720):
    img = Image.open(input_path).convert("RGB")
    img = _crop_cover(img, width, height)

    img = ImageEnhance.Contrast(img).enhance(1.25)
    img = ImageEnhance.Color(img).enhance(1.25)
    img = _apply_radial_vignette(img, strength=0.7)
    img = _apply_gaussian_grain(img, sigma=7.0)
    img.save(output_path, "JPEG", quality=95)


def process_documentary(input_path: str, output_path: str, width: int = 1280, height: int = 720):
    """
    Documentary grade: Desaturate to ~0.82, contrast ~1.28, radial vignette, light Gaussian grain (sigma ~6).
    """
    img = Image.open(input_path).convert("RGB")
    img = _crop_cover(img, width, height)

    img = ImageEnhance.Color(img).enhance(0.82)
    img = ImageEnhance.Contrast(img).enhance(1.28)
    img = _apply_radial_vignette(img, strength=0.6)
    img = _apply_gaussian_grain(img, sigma=6.0)
    img.save(output_path, "JPEG", quality=95)


def process_illustration(input_path: str, output_path: str, width: int = 1280, height: int = 720):
    """
    Illustration rescue: Smooth, saturate ~1.35, posterize to 4 bits, blend ~18% of inverted edge-detect pass, vignette & grain.
    """
    img = Image.open(input_path).convert("RGB")
    img = _crop_cover(img, width, height)

    img = img.filter(ImageFilter.SMOOTH)
    img = ImageEnhance.Color(img).enhance(1.35)
    img = ImageOps.posterize(img, 4)

    gray = img.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    inv_edges = ImageOps.invert(edges).convert("RGB")

    img = Image.blend(img, inv_edges, 0.18)
    img = _apply_radial_vignette(img, strength=0.55)
    img = _apply_gaussian_grain(img, sigma=5.0)
    img.save(output_path, "JPEG", quality=95)


def process_silhouette(input_path: str, output_path: str, width: int = 1280, height: int = 720):
    """
    Silhouette rescue: Brightness ~0.78, contrast ~2.1, saturation ~0.7, strong vignette.
    Crushes midtones so shapes read and detail disappears.
    """
    img = Image.open(input_path).convert("RGB")
    img = _crop_cover(img, width, height)

    img = ImageEnhance.Brightness(img).enhance(0.78)
    img = ImageEnhance.Contrast(img).enhance(2.1)
    img = ImageEnhance.Color(img).enhance(0.7)
    img = _apply_radial_vignette(img, strength=0.85)
    img.save(output_path, "JPEG", quality=95)
