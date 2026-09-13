"""Report photos: nothing but the pixels survives, and bad files are refused."""

import io

import pytest
from PIL import Image

from app.services.report_photos import MAX_EDGE, PhotoRejected, clean_photo, clean_photos

GPS_IFD = 0x8825
ORIENTATION = 0x0112


def photo_with_gps_and_rotation(width: int = 60, height: int = 30) -> bytes:
    image = Image.new("RGB", (width, height), "red")
    exif = image.getexif()
    exif[ORIENTATION] = 6  # "rotate 90° to display"
    exif[0x010F] = "PhoneMaker"
    exif.get_ifd(GPS_IFD).update({1: "N", 2: (5.0, 33.0, 0.0), 3: "W", 4: (0.0, 12.0, 0.0)})
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif.tobytes(), comment=b"taken at home")
    return out.getvalue()


def test_gps_and_every_other_trace_of_the_original_file_is_gone() -> None:
    original = photo_with_gps_and_rotation()
    assert Image.open(io.BytesIO(original)).getexif().get_ifd(GPS_IFD)  # the fixture really has GPS

    cleaned = Image.open(io.BytesIO(clean_photo(original).data))
    assert cleaned.format == "JPEG"
    assert len(cleaned.getexif()) == 0
    assert not {"exif", "xmp", "comment", "icc_profile"} & set(cleaned.info)


def test_the_photo_is_turned_upright_before_its_orientation_tag_is_dropped() -> None:
    cleaned = clean_photo(photo_with_gps_and_rotation(width=60, height=30))
    assert (cleaned.width, cleaned.height) == (30, 60)


def test_large_photos_are_scaled_down() -> None:
    out = io.BytesIO()
    Image.new("RGB", (4000, 1000), "blue").save(out, format="PNG")
    cleaned = clean_photo(out.getvalue())
    assert max(cleaned.width, cleaned.height) == MAX_EDGE


@pytest.mark.parametrize("data", [b"%PDF-1.4 not a photo", b"", b"GIF89a" + b"\x00" * 20])
def test_anything_but_a_jpeg_png_or_webp_is_refused(data: bytes) -> None:
    with pytest.raises(PhotoRejected):
        clean_photo(data, 3)


def test_at_most_ten_photos() -> None:
    with pytest.raises(PhotoRejected, match="at most 10"):
        clean_photos([photo_with_gps_and_rotation()] * 11)
