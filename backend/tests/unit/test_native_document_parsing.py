"""真实 Office / PDF 样本以及文本格式和损坏输入的本地解析。"""

from io import BytesIO
from pathlib import Path

import pytest

from tools.documents.parsing import MAX_FILE_BYTES, parse_file

FIXTURES = Path(__file__).parents[1] / "fixtures/documents"


@pytest.mark.parametrize(
    "extension, marker",
    [
        ("docx", "AIP-DOCX-119"),
        ("xlsx", "AIP-XLSX-119"),
        ("pptx", "AIP-PPTX-119"),
        ("pdf", "AIP-PDF-119"),
    ],
)
def test_real_office_and_text_pdf_without_external_parser(extension, marker):
    path = FIXTURES / f"sample.{extension}"
    with path.open("rb") as handle:
        blocks = parse_file(handle, path.name)
    assert marker in str(blocks)
    assert all(block.get("source") and block.get("block_id") for block in blocks)


@pytest.mark.parametrize(
    "name,data,marker",
    [
        ("note.txt", "照明节能 38%".encode(), "38%"),
        ("note.txt", "中文 GB18030".encode("gb18030"), "中文"),
        ("note.md", b"# Header\n\nAIP-MD-119", "AIP-MD-119"),
        ("table.csv", b"Road,Before,After\nAIP-CSV-119,1000,620\n", "620"),
    ],
)
def test_plain_formats_are_parsed_locally(name, data, marker):
    assert marker in str(parse_file(BytesIO(data), name))


@pytest.mark.parametrize(
    "name,data",
    [
        ("empty.txt", b""),
        ("blank.txt", b" \n\n"),
        ("bad.docx", b"not zip"),
        ("bad.pdf", b"not PDF"),
        ("picture.png", b"PNG"),
        ("old.doc", b"old Word"),
    ],
)
def test_empty_corrupt_and_unsupported_files_are_not_reported_as_parsed(name, data):
    with pytest.raises(ValueError):
        parse_file(BytesIO(data), name)


def test_file_size_limit_is_checked_before_parsing():
    with pytest.raises(ValueError, match="25 MB"):
        parse_file(BytesIO(b"x" * (MAX_FILE_BYTES + 1)), "big.txt")
