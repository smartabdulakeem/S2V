import subprocess
import os

def _run_magick(cmd: list[str]):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ImageMagick failed: {result.stderr}")

def process_vignette(input_path: str, output_path: str, width: int = 1280, height: int = 720):
    cmd = [
        "magick", "convert", input_path,
        "-resize", f"{width}x{height}^", "-gravity", "center", "-crop", f"{width}x{height}+0+0",
        "-background", "black", "-vignette", "0x20",
        "-attenuate", "0.5", "+noise", "Gaussian",
        output_path
    ]
    _run_magick(cmd)

def process_diptych(img1_path: str, img2_path: str, output_path: str, width: int = 1280, height: int = 720):
    half_width = width // 2
    cmd = [
        "magick", "convert",
        "(", img1_path, "-resize", f"{half_width}x{height}^", "-gravity", "center", "-crop", f"{half_width}x{height}+0+0", ")",
        "(", img2_path, "-resize", f"{half_width}x{height}^", "-gravity", "center", "-crop", f"{half_width}x{height}+0+0", ")",
        "+append",
        "-background", "black", "-vignette", "0x20",
        "-attenuate", "0.5", "+noise", "Gaussian",
        output_path
    ]
    _run_magick(cmd)

def process_collage(img1_path: str, img2_path: str, output_path: str, width: int = 1280, height: int = 720):
    half_width = width // 2
    cmd = [
        "magick", "convert",
        "(", img1_path, "-resize", f"{half_width}x{height}^", "-gravity", "center", "-crop", f"{half_width}x{height}+0+0", ")",
        "(", img2_path, "-resize", f"{half_width}x{height}^", "-gravity", "center", "-crop", f"{half_width}x{height}+0+0", ")",
        "+append",
        "-background", "black", "-vignette", "0x20",
        output_path
    ]
    _run_magick(cmd)

def process_vox_collage(input_path: str, output_path: str, width: int = 1280, height: int = 720):
    """
    Applies Vox Paper-Collage post-processing: high contrast, newsprint saturation boost, 
    paper-grain texture (+noise Gaussian), and dark editorial vignette.
    """
    cmd = [
        "magick", "convert", input_path,
        "-resize", f"{width}x{height}^", "-gravity", "center", "-crop", f"{width}x{height}+0+0",
        "-contrast-stretch", "1%x1%",
        "-modulate", "105,125,100",
        "-background", "#111111", "-vignette", "0x25",
        "-attenuate", "0.35", "+noise", "Gaussian",
        output_path
    ]
    _run_magick(cmd)

