"""Text extraction from PDF files, one string per page (pypdfium2, ADR 0007)."""

from pathlib import Path

import pypdfium2


def extract_pages(path: Path) -> list[str]:
    """Return the text of every page in order; page i of the list is PDF page i + 1.

    Line breaks are normalized to "\\n". A page without a text layer gives "".
    Raises FileNotFoundError if path does not exist.
    """
    if not path.is_file():
        raise FileNotFoundError(path)
    document = pypdfium2.PdfDocument(path)
    try:
        pages = []
        for index in range(len(document)):
            page = document[index]
            textpage = page.get_textpage()
            text = textpage.get_text_bounded()
            textpage.close()
            page.close()
            pages.append(text.replace("\r\n", "\n").replace("\r", "\n"))
        return pages
    finally:
        document.close()


def library_version() -> str:
    """Return the pypdfium2 version, recorded in the pipeline version of each filing."""
    return str(pypdfium2.version.PYPDFIUM_INFO)
