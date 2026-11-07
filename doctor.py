"""Offline portability check: imports, bundled OCR, and idle UI. No game reads."""
import bootstrap
import hashlib
import platform
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


def main():
    if sys.platform!='win32' or sys.version_info[:2]!=(3,12) or sys.maxsize<=2**32:
        raise SystemExit('Supported: Windows x64 / Python 3.12 x64.')
    import cv2
    import numpy
    import onnxruntime
    import tkinter as tk
    from ui_runtime import ctk as customtkinter
    from PIL import Image
    from pixel_ocr import model
    from catalog import Catalog
    import app
    for name in ('en-rec.onnx','msg_font.npz','monsters.json','map_overrides.json'):
        path=bootstrap.ROOT/'assets'/name
        if not path.is_file():raise RuntimeError(f'Missing asset: {name}')
    assert hashlib.sha256((bootstrap.ROOT/'assets/en-rec.onnx').read_bytes()).hexdigest()=='ef7abd8bd3629ae57ea2c28b425c1bd258a871b93fd2fe7c433946ade9b5d9ea'
    print(f'Python {platform.python_version()} x64; ONNX {onnxruntime.__version__}; UI {customtkinter.__version__}')
    assert Catalog().maps
    reader=model()
    reader(Image.new('RGB',(320,70),'white'))
    temp_root=bootstrap.ROOT/'.tmp'
    temp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_root) as temporary:
        with patch.object(app,'CONFIG',Path(temporary)/'settings.json'), \
             patch.object(app.capture,'enumerate_windows',return_value=[]), \
             patch.object(app.capture,'grab_region',side_effect=AssertionError('Unexpected capture')):
            root=tk.Tk();root.withdraw();ui=app.App(root)
            try:
                root.update_idletasks()
                assert not ui.running and ui.last_frame is None
            finally:ui.close()
    print('PASS: bundled model, catalogue and idle UI work. No screenshots captured.')


if __name__=='__main__':main()
