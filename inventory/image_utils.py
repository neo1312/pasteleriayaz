import io
import os
import re
import unicodedata

from django.core.files.base import ContentFile
from PIL import Image, ImageOps


DEFAULT_MAX_WIDTH = 800
GALLERY_MAX_WIDTH = 1200
GALLERY_WIDTH = 1200
GALLERY_HEIGHT = 1600
DEFAULT_QUALITY = 82


def _sanitize_filename(name):
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r'[^A-Za-z0-9._-]+', '_', name)
    name = re.sub(r'_{2,}', '_', name).strip('_')
    return name or 'image'


def optimize_image(source, max_width=DEFAULT_MAX_WIDTH, quality=DEFAULT_QUALITY, target_size=None):
    """Return (bytes, filename) of an optimized WebP version of ``source``.

    ``source`` may be a file path (str) or an opened PIL.Image.
    When ``target_size`` (width, height) is given, the image is center-cropped
    to that exact ratio/size; otherwise it is only downscaled to ``max_width``.
    """
    if isinstance(source, Image.Image):
        img = source
        base_name = getattr(source, 'filename', None) or 'image'
    else:
        img = Image.open(source)
        base_name = os.path.basename(str(source))
    base_name = _sanitize_filename(base_name)
    if base_name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
        base_name = base_name.rsplit('.', 1)[0]
    base_name = base_name + '.webp'

    img = ImageOps.exif_transpose(img)
    img = img.convert('RGB')
    if target_size:
        img = ImageOps.fit(img, target_size, method=Image.LANCZOS, centering=(0.5, 0.5))
    elif img.width > max_width:
        new_height = round(img.height * max_width / img.width)
        img = img.resize((max_width, new_height), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format='WEBP', quality=quality, method=6, optimize=True)
    return buf.getvalue(), base_name


def _optimized_content_file(uploaded_file, max_width=DEFAULT_MAX_WIDTH, quality=DEFAULT_QUALITY, target_size=None):
    if not uploaded_file:
        return None
    data, filename = optimize_image(uploaded_file, max_width=max_width, quality=quality, target_size=target_size)
    return ContentFile(data, name=filename)


def save_optimized_product_image(uploaded_file, upload_dir='products/'):
    """Optimize an uploaded image and return a ContentFile (or None).

    The returned ContentFile is meant to be assigned to Product.image before
    calling save(). Returns None if the upload is empty.
    """
    return _optimized_content_file(uploaded_file)


def save_optimized_gallery_image(uploaded_file):
    """Crop to 3:4 (1200x1600) and optimize a gallery upload into a WebP ContentFile."""
    return _optimized_content_file(
        uploaded_file,
        max_width=GALLERY_MAX_WIDTH,
        target_size=(GALLERY_WIDTH, GALLERY_HEIGHT),
    )
