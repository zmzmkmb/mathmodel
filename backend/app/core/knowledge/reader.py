"""文档读取器 —— 本地 PDF/DOCX/DOC 文本提取，不依赖 LLM。"""

from __future__ import annotations

import json as json_mod
from pathlib import Path

import fitz  # pymupdf


class DocumentReader:
    """从 PDF / DOCX 文件中提取纯文本。"""

    # ---- PDF ----

    @staticmethod
    def read_pdf(path: str | Path) -> str:
        """读取 PDF 全文，返回纯文本。"""
        doc = fitz.open(str(path))
        try:
            pages: list[str] = []
            for page in doc:
                text = page.get_text()
                if text.strip():
                    pages.append(text.strip())
            return "\n\n".join(pages)
        finally:
            doc.close()

    # ---- DOCX ----

    @staticmethod
    def read_docx(path: str | Path) -> str:
        """读取 DOCX 全文，返回纯文本。"""
        from docx import Document  # type: ignore[import-untyped]

        doc = Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)

    # ---- 统一入口 ----

    @classmethod
    def read(cls, path: str | Path) -> str:
        """根据后缀自动选择读取方式。"""
        path = Path(path)
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return cls.read_pdf(path)
        if suffix in (".docx", ".doc"):
            return cls.read_docx(path)
        # 纯文本直接读
        if suffix in (".txt", ".md"):
            return path.read_text(encoding="utf-8", errors="replace")
        raise ValueError(f"不支持的文件格式: {suffix}")

    @classmethod
    def read_or_none(cls, path: str | Path) -> str | None:
        """读取文件，失败返回 None 而不抛异常。"""
        try:
            return cls.read(path)
        except Exception:
            return None


def extract_papers(
    papers_dir: str | Path,
    output_path: str | Path,
    *,
    extensions: tuple[str, ...] = (".pdf", ".docx", ".doc"),
    resume: bool = True,
) -> dict[str, dict]:
    """批量从论文目录提取文本，写入 JSON。

    Args:
        papers_dir: 论文根目录（如 E:/桌面/1-优秀论文/）。
        output_path: 输出 JSON 文件路径。
        extensions: 要处理的文件后缀。
        resume: True 时跳过已有条目，仅处理新文件。

    Returns:
        {paper_id: {year, source_path, text}} 的完整字典。
    """
    papers_dir = Path(papers_dir)
    output_path = Path(output_path)

    # 恢复已有数据
    existing: dict[str, dict] = {}
    if resume and output_path.exists():
        try:
            existing = json_mod.loads(output_path.read_text(encoding="utf-8"))
        except (json_mod.JSONDecodeError, ValueError):
            existing = {}

    # 收集所有论文文件
    files: list[Path] = []
    for ext in extensions:
        files.extend(papers_dir.rglob(f"*{ext}"))
    files.sort(key=lambda f: (f.parent.name, f.name))

    total = len(files)
    processed = 0
    skipped = 0
    failed = 0

    for fp in files:
        paper_id = f"{fp.parent.name}_{fp.stem}"
        if resume and paper_id in existing:
            skipped += 1
            continue

        text = DocumentReader.read_or_none(fp)
        if text is None:
            failed += 1
            continue

        existing[paper_id] = {
            "year": fp.parent.name,
            "source_path": str(fp),
            "text": text,
        }
        processed += 1

        # 每 10 篇保存一次（保护进度）
        if processed % 10 == 0:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json_mod.dumps(existing, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"  已保存: {processed} 处理, {skipped} 跳过, {failed} 失败 (共 {total})")

    # 最终保存
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json_mod.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n完成: {processed} 新处理, {skipped} 跳过, {failed} 失败, 共 {len(existing)} 条")
    return existing
