"""维护可核验、可导出的数学建模参考文献登记表。"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_registry() -> dict[str, Any]:
    """创建空文献登记表。"""
    return {"schema_version": SCHEMA_VERSION, "references": [], "updated_at": _now()}


def load_registry(path: Path) -> dict[str, Any]:
    """读取登记表。"""
    if not path.exists():
        raise FileNotFoundError(f"文献登记表不存在：{path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("references"), list):
        raise ValueError("literature.json 格式无效")
    return data


def save_registry(path: Path, registry: dict[str, Any]) -> None:
    """原子写入登记表。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    registry["updated_at"] = _now()
    payload = json.dumps(registry, ensure_ascii=False, indent=2) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        Path(temp_name).replace(path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def validate_registry(registry: dict[str, Any]) -> list[str]:
    """检查重复、元数据、核验来源和正文用途。"""
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_dois: set[str] = set()
    current_year = datetime.now(timezone.utc).year
    for index, reference in enumerate(registry.get("references", []), start=1):
        ref_id = str(reference.get("id", "")).strip()
        title = str(reference.get("title", "")).strip()
        if not ref_id:
            errors.append(f"第 {index} 条缺少 id")
        elif ref_id in seen_ids:
            errors.append(f"重复文献 id：{ref_id}")
        seen_ids.add(ref_id)
        if not title:
            errors.append(f"文献 {ref_id or index} 缺少 title")
        if not reference.get("authors"):
            errors.append(f"文献 {ref_id or index} 缺少 authors")
        year = reference.get("year")
        if not isinstance(year, int) or year < 1800 or year > current_year:
            errors.append(f"文献 {ref_id or index} 的 year 无效")
        doi = str(reference.get("doi", "")).strip().lower()
        if doi:
            if not DOI_RE.match(doi):
                errors.append(f"文献 {ref_id or index} 的 DOI 格式无效")
            if doi in seen_dois:
                errors.append(f"重复 DOI：{doi}")
            seen_dois.add(doi)
        if not doi and not str(reference.get("url", "")).strip():
            errors.append(f"文献 {ref_id or index} 缺少 DOI 或 URL")
        if reference.get("verification_status") == "verified" and not reference.get("verified_sources"):
            errors.append(f"文献 {ref_id or index} 标记 verified 但没有核验来源")
        if reference.get("verification_status") != "verified":
            errors.append(f"文献 {ref_id or index} 尚未核验，不得进入最终参考文献")
        if not reference.get("used_in"):
            errors.append(f"文献 {ref_id or index} 未登记正文用途 used_in")
    return errors


def _citation(reference: dict[str, Any]) -> str:
    """生成简洁、可复核的参考文献文本。"""
    authors = ", ".join(reference.get("authors", []))
    title = reference.get("title", "")
    venue = reference.get("venue", "")
    year = reference.get("year", "")
    suffix = f" DOI: {reference['doi']}" if reference.get("doi") else f" {reference.get('url', '')}"
    return f"{authors}. {title}. {venue}, {year}.{suffix}".replace(". ,", ".")


def export_registry(registry: dict[str, Any], output_format: str) -> str:
    """导出 Markdown、Typst 或 LaTeX 参考文献块。"""
    references = registry.get("references", [])
    if output_format == "markdown":
        return "\n".join(
            f"[{index}] {_citation(reference)}"
            for index, reference in enumerate(references, start=1)
        ) + "\n"
    if output_format == "typst":
        lines = ["#set enum(numbering: \"[1]\")", "#enum["]
        lines.extend(f"  {_citation(reference)}" for reference in references)
        lines.append("]")
        return "\n".join(lines) + "\n"
    lines = ["\\begin{thebibliography}{99}"]
    for reference in references:
        lines.append(f"  \\bibitem{{{reference['id']}}} {_citation(reference)}")
    lines.append("\\end{thebibliography}")
    return "\n".join(lines) + "\n"


def main() -> int:
    """执行文献登记、校验和导出命令。"""
    parser = argparse.ArgumentParser(description="维护 literature.json")
    parser.add_argument("--path", default="data/literature.json")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--force", action="store_true")

    add_parser = subparsers.add_parser("add")
    add_parser.add_argument("--id", required=True)
    add_parser.add_argument("--title", required=True)
    add_parser.add_argument("--authors", required=True, help="作者用分号分隔")
    add_parser.add_argument("--year", type=int, required=True)
    add_parser.add_argument("--venue", default="")
    add_parser.add_argument("--doi", default="")
    add_parser.add_argument("--url", default="")
    add_parser.add_argument("--source", default="")
    add_parser.add_argument("--verified-source", action="append", default=[])
    add_parser.add_argument("--used-in", action="append", default=[])
    add_parser.add_argument(
        "--verification-status",
        choices=("unverified", "verified"),
        default="unverified",
    )

    subparsers.add_parser("validate")
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--format", choices=("markdown", "typst", "latex"), required=True)
    export_parser.add_argument("--output", required=True)
    subparsers.add_parser("show")

    args = parser.parse_args()
    path = Path(args.path)
    if args.command == "init":
        if not path.exists() or args.force:
            save_registry(path, new_registry())
        print(path)
        return 0

    registry = load_registry(path)
    if args.command == "add":
        references = registry.setdefault("references", [])
        references[:] = [reference for reference in references if reference.get("id") != args.id]
        references.append({
            "id": args.id,
            "title": args.title.strip(),
            "authors": [author.strip() for author in args.authors.split(";") if author.strip()],
            "year": args.year,
            "venue": args.venue.strip(),
            "doi": args.doi.strip(),
            "url": args.url.strip(),
            "source": args.source.strip(),
            "verified_sources": args.verified_source,
            "verification_status": args.verification_status,
            "used_in": args.used_in,
            "updated_at": _now(),
        })
        save_registry(path, registry)
        print(args.id)
        return 0
    if args.command == "validate":
        errors = validate_registry(registry)
        print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    if args.command == "export":
        errors = validate_registry(registry)
        if errors:
            print(json.dumps({"valid": False, "errors": errors}, ensure_ascii=False, indent=2))
            return 1
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(export_registry(registry, args.format), encoding="utf-8")
        print(output)
        return 0
    print(json.dumps(registry, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
