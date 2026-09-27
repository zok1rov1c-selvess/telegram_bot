"""Unicode (o'zbek lotin/kirill) shriftlarini topish yoki yuklab olish."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx

from config import ASSETS_DIR

log = logging.getLogger(__name__)

NOTO_REGULAR = (
    "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/"
    "NotoSans/NotoSans-Regular.ttf"
)
NOTO_BOLD = (
    "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/"
    "NotoSans/NotoSans-Bold.ttf"
)

CANDIDATES = [
    # Windows
    (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
    (r"C:\Windows\Fonts\tahoma.ttf", r"C:\Windows\Fonts\tahomabd.ttf"),
    # Linux
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    # macOS
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
]


def _download(url: str, dest: Path) -> bool:
    try:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            r = client.get(url)
            r.raise_for_status()
            dest.write_bytes(r.content)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Shriftni yuklab bo'lmadi (%s): %s", url, exc)
        return False


def get_unicode_fonts() -> tuple[str, str]:
    """(regular_ttf, bold_ttf) yo'llarini qaytaradi."""
    bundled_r = ASSETS_DIR / "NotoSans-Regular.ttf"
    bundled_b = ASSETS_DIR / "NotoSans-Bold.ttf"
    if bundled_r.exists() and bundled_b.exists():
        return str(bundled_r), str(bundled_b)

    for reg, bold in CANDIDATES:
        if os.path.exists(reg):
            return reg, bold if os.path.exists(bold) else reg

    if _download(NOTO_REGULAR, bundled_r) and _download(NOTO_BOLD, bundled_b):
        return str(bundled_r), str(bundled_b)

    raise RuntimeError("Unicode shrift topilmadi. assets/ papkasiga .ttf shrift qo'ying.")
