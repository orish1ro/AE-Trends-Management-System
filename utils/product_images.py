import base64
import os

from PyQt6.QtCore import QBuffer, QIODevice, QSize, Qt
from PyQt6.QtGui import QImage, QImageReader, QPainter

from utils.validators import ValidationError

MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_IMAGE_DIMENSION = 1080
JPEG_QUALITY = 80


def compress_product_image(path):
    if not path or not os.path.isfile(path):
        raise ValidationError("Please upload a valid image file.")
    if os.path.getsize(path) > MAX_IMAGE_BYTES:
        raise ValidationError(
            "File size too large. Please upload an image under 25MB.")

    reader = QImageReader(path)
    reader.setAutoTransform(True)
    if not reader.canRead():
        raise ValidationError("Please upload a valid image file.")

    original_size = reader.size()
    if original_size.isValid() and (
        original_size.width() > MAX_IMAGE_DIMENSION
        or original_size.height() > MAX_IMAGE_DIMENSION
    ):
        reader.setScaledSize(original_size.scaled(
            QSize(MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION),
            Qt.AspectRatioMode.KeepAspectRatio,
        ))

    image = reader.read()
    if image.isNull():
        raise ValidationError("Please upload a valid image file.")

    if image.width() > MAX_IMAGE_DIMENSION or image.height() > MAX_IMAGE_DIMENSION:
        image = image.scaled(
            QSize(MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    if image.hasAlphaChannel():
        flattened = QImage(image.size(), QImage.Format.Format_RGB32)
        flattened.fill(Qt.GlobalColor.white)
        painter = QPainter(flattened)
        painter.drawImage(0, 0, image)
        painter.end()
        image = flattened
    else:
        image = image.convertToFormat(QImage.Format.Format_RGB32)

    output = QBuffer()
    if not output.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError("Could not open image compression buffer.")
    try:
        if not image.save(output, "JPEG", JPEG_QUALITY):
            raise OSError("Could not compress product image.")
        encoded = base64.b64encode(output.data().data()).decode("ascii")
    finally:
        output.close()

    return f"data:image/jpeg;base64,{encoded}"
