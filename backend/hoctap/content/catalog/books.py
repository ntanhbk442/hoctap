"""The code-owned catalogue of the Toán Books.

This table is the only source of truth: nothing is discovered by globbing. The
`book_id`s are permanent (AD-3). Source paths are relative to `Settings.source_dir`
(`Sach_Arch/`), use `/` as separator and are NFC-normalised.

Skipped duplicates (the full-quality file of each pair is listed instead):
`Huong_Dan_Hoc_Toan_1_Tap_1_..._2024_2025-compressed.pdf`,
`Huong_Dan_Hoc_Toan_2_Tap_1_..._2024_2025-compressed.pdf` and
`Huong_Dan_Hoc_Toan_4_Tap_1_..._2024_2025-fromzip.pdf`.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

EDITION_2020 = "2020"
EDITION_2024 = "2024-25"


@dataclass(frozen=True)
class CatalogueBook:
    book_id: str
    edition: str
    grade: int
    volume: int
    source_path: str

    @property
    def title_vi(self) -> str:
        if self.edition == EDITION_2020:
            return f"Toán {self.grade} – Quyển {self.volume} (2020)"
        return f"Toán {self.grade} – Tập {self.volume} (2024–25)"


def _b2020(grade: int, volume: int, path: str) -> CatalogueBook:
    return CatalogueBook(f"toan{grade}-2020-q{volume}", EDITION_2020, grade, volume, path)


def _b2024(grade: int, volume: int, file_name: str) -> CatalogueBook:
    return CatalogueBook(
        f"toan{grade}-2024-t{volume}", EDITION_2024, grade, volume, f"Sach_moi/{file_name}"
    )


_HDH = "Huong_Dan_Hoc_Toan_{g}_Tap_{t}_Archimede_2024_2025{suffix}.pdf"
_TOAN5_2024 = "Hướng dẫn học Toán Lớp 5 Trường Archimedes Quyển {t} mới nhất 2024.pdf"

_BOOKS: tuple[CatalogueBook, ...] = (
    # 2020 edition: 4 volumes (Quyển) per grade.
    *(_b2020(1, q, f"Lớp 1/toán q{q}.pdf") for q in range(1, 5)),
    _b2020(2, 1, "Lớp 2/Toán Arc - Lớp 2- Quyển 1.pdf"),
    _b2020(2, 2, "Lớp 2/Toán Arc- lớp 2-quyển 2.pdf"),
    _b2020(2, 3, "Lớp 2/Toán Arc - lớp 2 - quyển 3.pdf"),
    _b2020(2, 4, "Lớp 2/Toán Arc - Lớp 2- quyển 4.pdf"),
    _b2020(3, 1, "Lớp 3/Toan 3- Q1.pdf"),
    _b2020(3, 2, "Lớp 3/Toan 3- Q2.pdf"),
    _b2020(3, 3, "Lớp 3/Toan 3-Q3.pdf"),
    _b2020(3, 4, "Lớp 3/Toan3 -Q4.pdf"),
    *(_b2020(4, q, f"Lớp 4/toasn 4 q{q}.pdf") for q in range(1, 5)),
    *(_b2020(5, q, f"Lớp 5/toán lớp 5 q{q}.pdf") for q in range(1, 5)),
    # 2024-25 edition: 2 volumes (Tập) per grade.
    _b2024(1, 1, _HDH.format(g=1, t=1, suffix="")),
    _b2024(1, 2, _HDH.format(g=1, t=2, suffix="")),
    _b2024(2, 1, _HDH.format(g=2, t=1, suffix="")),
    _b2024(2, 2, _HDH.format(g=2, t=2, suffix="-compressed")),
    _b2024(3, 1, _HDH.format(g=3, t=1, suffix="-compressed")),
    _b2024(3, 2, _HDH.format(g=3, t=2, suffix="-compressed")),
    _b2024(4, 1, _HDH.format(g=4, t=1, suffix="")),
    _b2024(4, 2, _HDH.format(g=4, t=2, suffix="")),
    _b2024(5, 1, _TOAN5_2024.format(t=1)),
    _b2024(5, 2, _TOAN5_2024.format(t=2)),
)

# NFC everywhere, whatever form this source file was saved in.
BOOKS: tuple[CatalogueBook, ...] = tuple(
    CatalogueBook(
        b.book_id, b.edition, b.grade, b.volume, unicodedata.normalize("NFC", b.source_path)
    )
    for b in _BOOKS
)
