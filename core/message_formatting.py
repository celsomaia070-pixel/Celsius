"""Readable WhatsApp text from chat markdown, without wide pipe tables."""

import re


def table_cells(line: str) -> list[str]:
    return [
        cell.strip().replace(r"\|", "|") for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))
    ]


def whatsapp_text(text: str) -> str:
    lines = str(text or "").replace("\r\n", "\n").split("\n")
    output = []
    index = 0
    in_code = False
    while index < len(lines):
        line = lines[index]
        if line.strip().startswith("```"):
            in_code = not in_code
            output.append("```")
            index += 1
            continue
        if not in_code and "|" in line and index + 1 < len(lines):
            separators = table_cells(lines[index + 1])
            if separators and all(re.fullmatch(r":?-{3,}:?", c) for c in separators):
                headers = table_cells(line)
                index += 2
                while index < len(lines) and "|" in lines[index] and lines[index].strip():
                    cells = table_cells(lines[index])
                    output.append("• " + (cells[0] if cells else ""))
                    for label, value in zip(headers[1:], cells[1:], strict=False):
                        if value:
                            output.append(f"  {label}: {value}")
                    output.append("")
                    index += 1
                continue
        if not in_code:
            line = re.sub(r"^\s*#{1,6}\s+(.+)$", r"*\1*", line)
            line = re.sub(r"\*\*(.+?)\*\*", r"*\1*", line)
            line = re.sub(r"!\[([^]]*)\]\([^)]+\)", r"\1 (imagem disponível no computador)", line)

            def _replace_link(match: re.Match) -> str:
                label = match.group(1)
                url = match.group(2)
                if isinstance(url, str) and url.startswith(("https://", "http://")):
                    return f"{label}: {url}"
                return label

            line = re.sub(r"\[([^]]+)\]\(([^)]+)\)", _replace_link, line)
            if re.fullmatch(r"\s*[-_*]{3,}\s*", line):
                line = ""
        output.append(line)
        index += 1
    return re.sub(r"\n{3,}", "\n\n", "\n".join(output)).strip()


def whatsapp_chunks(text: str, limit: int = 3500) -> list[str]:
    text = whatsapp_text(text)
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        boundary = text.rfind("\n\n", 0, limit + 1)
        if boundary < limit // 3:
            boundary = text.rfind("\n", 0, limit + 1)
        if boundary < limit // 3:
            boundary = text.rfind(" ", 0, limit + 1)
        if boundary <= 0:
            boundary = limit
        chunks.append(text[:boundary])
        text = text[boundary:].lstrip()
    return chunks
