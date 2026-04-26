"""灰机wiki星网页面爬虫，获取卫星发射组数据。

使用 curl_cffi 模拟浏览器 TLS 指纹绕过 Cloudflare 反爬。
"""

import re
from html.parser import HTMLParser

from curl_cffi import requests

HUIJI_URL = "https://sat.huijiwiki.com/wiki/%E6%98%9F%E7%BD%91"


class WikitableParser(HTMLParser):
    """解析 HTML 表格，提取单元格文本内容。"""

    def __init__(self):
        super().__init__()
        self.in_cell = False
        self.current_cell = ""
        self.rows: list[list[str]] = []
        self.current_row: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.current_row = []
        elif tag in ("td", "th"):
            self.in_cell = True
            self.current_cell = ""

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.in_cell:
            self.in_cell = False
            self.current_row.append(self.current_cell.strip())
        elif tag == "tr" and self.current_row:
            self.rows.append(self.current_row)

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell += data


def fetch_page(url: str = HUIJI_URL, timeout: int | None = None) -> str:
    """获取页面 HTML，使用 curl_cffi 模拟浏览器 TLS 指纹绕过 Cloudflare。"""
    kwargs = {"impersonate": "chrome"}
    if timeout is not None:
        kwargs["timeout"] = timeout
    resp = requests.get(url, **kwargs)
    resp.raise_for_status()
    return resp.text


def _find_heading_positions(html: str) -> list[tuple[str, int]]:
    """找到所有标题及其位置。"""
    results = []
    for m in re.finditer(
        r'<span[^>]*class="mw-headline"[^>]*id="([^"]+)"[^>]*>(.*?)</span>', html
    ):
        results.append((m.group(2), m.start()))
    return results


def _find_tables(html: str) -> list[re.Match]:
    """找到所有 wikitable。"""
    return list(
        re.finditer(
            r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>[\s\S]*?</table>', html
        )
    )


def parse_table_by_section(html: str, section_name: str) -> list[dict]:
    """
    根据标题定位 wikitable，提取指定段落的表格数据。

    返回: [{ "发射次数": ..., "名称": ..., ... }, ...]
    """
    headings = _find_heading_positions(html)
    tables = _find_tables(html)

    heading_pos = None
    for h_text, h_pos in headings:
        if h_text == section_name:
            heading_pos = h_pos
            break
    if heading_pos is None:
        raise ValueError(f"未找到'{section_name}'标题")

    # 找到该标题之后的第一个 wikitable
    target_table = None
    next_heading_pos = len(html)
    for _, h_pos in headings:
        if h_pos > heading_pos:
            next_heading_pos = min(next_heading_pos, h_pos)
            break

    for t in tables:
        if t.start() > heading_pos and t.start() < next_heading_pos:
            target_table = t
            break

    # 如果标题和下一个标题之间没找到，就往后找最近的
    if target_table is None:
        for t in tables:
            if t.start() > heading_pos:
                target_table = t
                break

    if target_table is None:
        raise ValueError(f"未找到{section_name}表格")

    parser = WikitableParser()
    parser.feed(target_table.group())

    if len(parser.rows) < 2:
        raise ValueError(f"{section_name}表格数据不足")

    headers = parser.rows[0]
    data = []
    for row in parser.rows[1:]:
        if len(row) < len(headers):
            continue
        entry = {}
        for i, h in enumerate(headers):
            if i < len(row):
                entry[h] = row[i]
        data.append(entry)

    return data


def fetch_satellite_groups() -> list[dict]:
    """获取星网业务星发射组数据。

    从灰机wiki爬取"业务星"表格，返回每组卫星的发射信息。
    每条记录包含：发射次数、名称、部署颗数、研制单位、发射时间、
    运载火箭、发射地点、轨道高度、轨道倾角、COSPAR、结果。
    """
    html = fetch_page()
    return parse_table_by_section(html, "业务星")
