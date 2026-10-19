"""普通附件的本地文本解析;不调用外部解析服务或模型。"""

from __future__ import annotations

import csv
import io
import posixpath
import re
import zipfile
from contextlib import closing
from pathlib import PurePosixPath
from typing import BinaryIO
from xml.etree import ElementTree as ET

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_DOCUMENTS = 10
MAX_TEXT_CHARACTERS = 1_000_000
MAX_EXPANDED_BYTES = 80 * 1024 * 1024
FORMATS = {
    ".txt": "UTF-8 / GB18030 文本",
    ".md": "Markdown 文本",
    ".csv": "CSV 行列数据",
    ".pdf": "PDF 文本层;不执行 OCR",
    ".docx": "Word 正文和表格;不读取图片",
    ".xlsx": "Excel 单元格存储值;不重新计算公式或读取图表",
    ".pptx": "PowerPoint 幻灯片文字;不读取图片",
}


def capabilities() -> dict:
    return {
        "formats": [{"extension": ext, "description": description} for ext, description in FORMATS.items()],
        "maxFileBytes": MAX_FILE_BYTES,
        "maxDocuments": MAX_DOCUMENTS,
        "limitations": "扫描 PDF 和图片暂不支持 OCR / 视觉分析;加密或损坏文件无法解析。",
    }


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("文本编码无法识别,请另存为 UTF-8 后重新上传。")


def _xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    data = archive.read(name)
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("文件包含不支持的 XML 实体声明。")
    return ET.fromstring(data)


def _texts(element: ET.Element, local_name: str = "t") -> str:
    return "".join(part.text or "" for part in element.iter() if part.tag.rsplit("}", 1)[-1] == local_name)


def _paragraph(text: str, source: str, **extra) -> dict:
    return {"type": "paragraph", "text": text, "source": source, **extra}


def _text_blocks(data: bytes, markdown: bool) -> list[dict]:
    blocks = []
    for number, line in enumerate(_decode(data).splitlines(), 1):
        if not line.strip():
            continue
        block = _paragraph(line, f"第 {number} 行", line=number)
        match = re.match(r"^(#{1,6})\s+(.+)$", line) if markdown else None
        if match:
            block.update(type="heading", level=len(match[1]), text=match[2])
        blocks.append(block)
    return blocks


def _csv_blocks(data: bytes) -> list[dict]:
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [row for row in csv.reader(io.StringIO(text), dialect) if any(cell.strip() for cell in row)]
    if not rows:
        return []
    return [
        {
            "type": "table",
            "headers": rows[0],
            "rows": rows[start : start + 100],
            "source": f"第 {start + 1}-{min(start + 100, len(rows))} 行",
        }
        for start in range(1, len(rows), 100)
    ] or [_paragraph(", ".join(rows[0]), "第 1 行")]


def _office_blocks(fileobj: BinaryIO, extension: str) -> list[dict]:
    with zipfile.ZipFile(fileobj) as archive:
        entries = archive.infolist()
        if len(entries) > 10000 or sum(entry.file_size for entry in entries) > MAX_EXPANDED_BYTES:
            raise ValueError("文件解压后过大,请拆分后上传。")
        if any(entry.flag_bits & 1 for entry in entries):
            raise ValueError("不支持加密文件,请移除密码后上传。")
        if extension == ".docx":
            root = _xml(archive, "word/document.xml")
            return [
                _paragraph(_texts(p), f"段落 {i}")
                for i, p in enumerate(root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"), 1)
                if _texts(p).strip()
            ]
        if extension == ".pptx":
            slides = sorted(
                (name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
                key=lambda name: int(re.search(r"slide(\d+)\.xml", name)[1]),
            )
            return [
                _paragraph(
                    "\n".join(
                        _texts(p)
                        for p in _xml(archive, name).iter("{http://schemas.openxmlformats.org/drawingml/2006/main}p")
                    ),
                    f"幻灯片 {i}",
                )
                for i, name in enumerate(slides, 1)
            ]

        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = [_texts(si) for si in _xml(archive, "xl/sharedStrings.xml")]
        relationships = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in _xml(archive, "xl/_rels/workbook.xml.rels")
            if rel.attrib.get("TargetMode") != "External"
        }
        blocks = []
        for sheet in _xml(archive, "xl/workbook.xml").findall("s:sheets/s:sheet", ns):
            relationship = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            target = relationships[relationship]
            name = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            for row in _xml(archive, name).findall("s:sheetData/s:row", ns):
                cells = []
                for cell in row.findall("s:c", ns):
                    value = cell.findtext("s:v", default="", namespaces=ns)
                    if cell.find("s:f", ns) is not None and not value:
                        raise ValueError("Excel 公式没有缓存结果,请在 Excel 中计算并保存后重新上传。")
                    if cell.attrib.get("t") == "s":
                        value = shared[int(value)]
                    elif cell.attrib.get("t") == "inlineStr":
                        value = _texts(cell)
                    if value:
                        cells.append(f"{cell.attrib.get('r', '')}: {value}")
                if cells:
                    blocks.append(
                        _paragraph(";".join(cells), f"工作表 {sheet.attrib['name']} · 第 {row.attrib.get('r', '?')} 行")
                    )
        return blocks


def _pdf_blocks(fileobj: BinaryIO) -> list[dict]:
    import pypdfium2 as pdfium

    from tools.documents.thumbnail import _PDFIUM_LOCK

    blocks = []
    notices = []
    with _PDFIUM_LOCK, pdfium.PdfDocument(fileobj) as pdf:
        if len(pdf) > 1000:
            raise ValueError("PDF 超过 1000 页,请拆分后上传。")
        for i in range(len(pdf)):
            with closing(pdf[i]) as page, closing(page.get_textpage()) as textpage:
                text = textpage.get_text_range().strip()
            if text:
                blocks.append(_paragraph(text, f"第 {i + 1} 页", page=i + 1))
            else:
                notices.append(f"第 {i + 1} 页没有可提取文本,可能为空白或扫描页;未执行 OCR。")
    if not blocks:
        raise ValueError("PDF 没有可提取的文本层,扫描件暂不支持 OCR。请上传文本型 PDF 或转换为 TXT。")
    if notices:
        blocks.insert(0, _paragraph("读取范围提示:" + " ".join(notices), "解析说明", notice=True))
    return blocks


def parse_file(fileobj: BinaryIO, filename: str) -> list[dict]:
    extension = PurePosixPath(filename).suffix.lower()
    if extension not in FORMATS:
        raise ValueError("暂不支持此格式。支持 TXT、Markdown、CSV、文本 PDF、DOCX、XLSX、PPTX。")
    fileobj.seek(0, 2)
    size = fileobj.tell()
    fileobj.seek(0)
    if not size:
        raise ValueError("文件为空,请选择包含内容的文件。")
    if size > MAX_FILE_BYTES:
        raise ValueError("文件超过 25 MB,请拆分后上传。")
    try:
        if extension in {".txt", ".md", ".csv"}:
            data = fileobj.read(MAX_FILE_BYTES + 1)
            blocks = _csv_blocks(data) if extension == ".csv" else _text_blocks(data, extension == ".md")
        elif extension == ".pdf":
            blocks = _pdf_blocks(fileobj)
        else:
            blocks = _office_blocks(fileobj, extension)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("文件损坏、加密或内部格式不正确,无法读取。请重新导出后上传。") from exc
    blocks = [block for block in blocks if block.get("text", "").strip() or block.get("rows")]
    if not blocks:
        raise ValueError("未提取到可分析的文本或表格,图片内容暂不支持识别。")
    if len(blocks) > 20000 or len(str(blocks)) > MAX_TEXT_CHARACTERS:
        raise ValueError("提取内容过长,请拆分为较小的文件。")
    for i, block in enumerate(blocks, 1):
        block["block_id"] = f"b{i}"
    return blocks
