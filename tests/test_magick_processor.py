import os
import tempfile
from PIL import Image
from pipeline.magick_processor import (
    process_vignette, process_diptych, process_collage, process_vox_collage,
    process_documentary, process_illustration, process_silhouette
)

def test_pillow_magick_processor_filters():
    with tempfile.TemporaryDirectory() as tmpdir:
        img1_path = os.path.join(tmpdir, "img1.jpg")
        img2_path = os.path.join(tmpdir, "img2.jpg")

        # Create dummy test images
        Image.new("RGB", (800, 600), color=(100, 150, 200)).save(img1_path)
        Image.new("RGB", (800, 600), color=(200, 100, 50)).save(img2_path)

        filters = [
            ("vignette", lambda out: process_vignette(img1_path, out, 640, 360)),
            ("diptych", lambda out: process_diptych(img1_path, img2_path, out, 640, 360)),
            ("collage", lambda out: process_collage(img1_path, img2_path, out, 640, 360)),
            ("vox_collage", lambda out: process_vox_collage(img1_path, out, 640, 360)),
            ("documentary", lambda out: process_documentary(img1_path, out, 640, 360)),
            ("illustration", lambda out: process_illustration(img1_path, out, 640, 360)),
            ("silhouette", lambda out: process_silhouette(img1_path, out, 640, 360)),
        ]

        for filter_name, func in filters:
            out_path = os.path.join(tmpdir, f"out_{filter_name}.jpg")
            func(out_path)
            assert os.path.exists(out_path), f"Output file for {filter_name} missing"
            out_img = Image.open(out_path)
            assert out_img.size == (640, 360), f"Incorrect dimensions for {filter_name}"
