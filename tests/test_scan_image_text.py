import os
import json
import pytest
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from tools import scan_image_text

def test_ocr_known_text_burned_and_clean_image(tmp_path, monkeypatch):
    """
    Real OCR run test:
    - Generated image with drawn 'HELLO WORLD' text lands in 'burned'
    - Plain gradient/solid photograph lands in 'clean'
    """
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    
    # 1. Create image with known text
    text_img_path = img_dir / "text_sample.jpg"
    img1 = Image.new("RGB", (640, 480), color=(240, 240, 240))
    draw1 = ImageDraw.Draw(img1)
    draw1.text((50, 100), "HELLO WORLD", fill=(0, 0, 0))
    draw1.text((50, 180), "AMERICAN CIVIL WAR INTRO SAMPLE", fill=(0, 0, 0))
    img1.save(text_img_path)

    # 2. Create plain image without text
    clean_img_path = img_dir / "clean_sample.jpg"
    img2 = Image.new("RGB", (640, 480), color=(100, 150, 200))
    img2.save(clean_img_path)

    monkeypatch.setattr(scan_image_text, "IMAGES_DIR", str(img_dir))
    monkeypatch.setattr(scan_image_text, "CACHE_FILE", str(tmp_path / "text_scan.jsonl"))
    monkeypatch.setattr(scan_image_text, "REPORT_HTML", str(tmp_path / "text_scan_report.html"))

    results, elapsed = scan_image_text.scan_images(force_rescan=True)

    rec_map = {os.path.basename(r["path"]): r for r in results}
    assert rec_map["text_sample.jpg"]["bucket"] == "burned"
    assert rec_map["clean_sample.jpg"]["bucket"] == "clean"


def test_scan_resumable_from_cache(tmp_path, monkeypatch):
    """
    Test that re-running scan_images resumes from cache rather than re-OCR scanning.
    """
    img_dir = tmp_path / "images"
    img_dir.mkdir()

    img_path = img_dir / "test_img.jpg"
    img = Image.new("RGB", (400, 300), color=(200, 200, 200))
    img.save(img_path)

    cache_file = tmp_path / "text_scan.jsonl"
    monkeypatch.setattr(scan_image_text, "IMAGES_DIR", str(img_dir))
    monkeypatch.setattr(scan_image_text, "CACHE_FILE", str(cache_file))
    monkeypatch.setattr(scan_image_text, "REPORT_HTML", str(tmp_path / "text_scan_report.html"))

    # Initial scan
    results1, _ = scan_image_text.scan_images(force_rescan=False)
    assert len(results1) == 1
    assert cache_file.exists()

    # Interrupted count check: patch RapidOCR to raise error if called on 2nd run
    def mock_rapid_ocr_error(*args, **kwargs):
        raise RuntimeError("RapidOCR engine called when cache should have been hit!")

    monkeypatch.setattr(scan_image_text, "RapidOCR", lambda: mock_rapid_ocr_error)

    # Second run — must hit cache and return 1 result without error
    results2, _ = scan_image_text.scan_images(force_rescan=False)
    assert len(results2) == 1
    assert results2[0]["sha256"] == results1[0]["sha256"]


def test_scan_without_quarantine_leaves_images_unchanged(tmp_path, monkeypatch):
    """
    Test that running scan_images without --quarantine leaves library/images/ file count unchanged.
    """
    img_dir = tmp_path / "images"
    img_dir.mkdir()

    for i in range(3):
        img_path = img_dir / f"img_{i}.jpg"
        img = Image.new("RGB", (300, 200), color=(i * 50, 100, 100))
        img.save(img_path)

    initial_count = len(list(img_dir.glob("*.jpg")))

    monkeypatch.setattr(scan_image_text, "IMAGES_DIR", str(img_dir))
    monkeypatch.setattr(scan_image_text, "CACHE_FILE", str(tmp_path / "text_scan.jsonl"))
    monkeypatch.setattr(scan_image_text, "REPORT_HTML", str(tmp_path / "text_scan_report.html"))

    results, _ = scan_image_text.scan_images(force_rescan=True)

    after_count = len(list(img_dir.glob("*.jpg")))
    assert initial_count == after_count == 3
