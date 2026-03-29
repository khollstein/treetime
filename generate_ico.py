"""Generate treetime.ico from the app's programmatic icon."""

import sys
import os
import struct
import io

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QBuffer, QIODevice
from ui.tray import create_app_icon


def icon_to_ico(icon, sizes, output_path):
    """Save a QIcon as a .ico file with multiple sizes."""
    entries = []
    for size in sizes:
        pixmap = icon.pixmap(size, size)
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buf, "PNG")
        png_data = bytes(buf.data())
        buf.close()
        entries.append((size, png_data))

    # ICO file format
    with open(output_path, "wb") as f:
        # Header: reserved(2) + type(2) + count(2)
        f.write(struct.pack("<HHH", 0, 1, len(entries)))

        # Calculate offsets
        header_size = 6 + len(entries) * 16
        offset = header_size

        # Directory entries
        for size, png_data in entries:
            w = size if size < 256 else 0
            h = size if size < 256 else 0
            f.write(struct.pack("<BBBBHHII",
                                w, h, 0, 0, 1, 32, len(png_data), offset))
            offset += len(png_data)

        # Image data
        for _, png_data in entries:
            f.write(png_data)


def main():
    app = QApplication(sys.argv)
    icon = create_app_icon(256)
    sizes = [16, 32, 48, 128, 256]
    output = os.path.join(os.path.dirname(os.path.abspath(__file__)), "treetime.ico")
    icon_to_ico(icon, sizes, output)
    print(f"Created {output}")


if __name__ == "__main__":
    main()
