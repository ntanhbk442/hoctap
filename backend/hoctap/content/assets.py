"""URLs of the served page images and crops (`/assets-data/*`).

The files are written by the builder under `data/assets/`: pages at
`pages/{book_id}/p{page:03d}.jpg`, crops at `crops/{book_id}/{problem_id}/{name}.jpg`
where name is an image_key, `_problem` (the first source page's bbox) or, for a Problem
spanning pages, `_problem_p{n}`.
"""

from __future__ import annotations

from hoctap.content.schema import ProblemDoc

ASSETS_URL = "/assets-data"


def page_url(book_id: str, page: int) -> str:
    return f"{ASSETS_URL}/pages/{book_id}/p{page:03d}.jpg"


def crop_url(book_id: str, problem_id: str, name: str) -> str:
    return f"{ASSETS_URL}/crops/{book_id}/{problem_id}/{name}.jpg"


def problem_crop_urls(doc: ProblemDoc) -> list[str]:
    """The whole-Problem crop(s) first, then one per image."""
    pages = sorted(p.page for p in doc.source_pages)
    names = ["_problem"]
    if len(pages) > 1:
        names += [f"_problem_p{n}" for n in pages]
    names += [i.image_key for i in doc.images]
    return [crop_url(doc.book_id, doc.problem_id, n) for n in names]


def problem_page_urls(doc: ProblemDoc) -> list[str]:
    return [page_url(doc.book_id, n) for n in sorted({p.page for p in doc.source_pages})]
