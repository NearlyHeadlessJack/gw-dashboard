"""火箭名称解析工具。"""

from __future__ import annotations

import re


def normalize_rocket_model_name(value: str | None) -> str | None:
    """返回火箭型号，去掉远征上面级等附加说明。"""
    cleaned = _clean_text(value)
    if not cleaned:
        return None

    cleaned = re.sub(r"\s*[/／]\s*远征.*$", "", cleaned)
    return _clean_text(cleaned)


def split_rocket_name_and_serial(value: str | None) -> tuple[str | None, str | None]:
    """把火箭字段拆成型号和箭体编号。"""
    cleaned = normalize_rocket_model_name(value)
    if not cleaned:
        return None, None

    match = re.match(
        r"^(?P<name>.+?)[\s（(]*(?P<serial>Y\s*\d+|遥\s*[\d零〇一二三四五六七八九十百]+)[）)]*$",
        cleaned,
        flags=re.IGNORECASE,
    )
    if not match:
        return cleaned, None

    name = match.group("name").strip()
    serial = re.sub(r"\s+", "", match.group("serial").upper())
    return name, serial


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None
