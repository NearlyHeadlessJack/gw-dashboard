"""Tests for gw.scraper.huiji — offline parser and fetch orchestration tests."""

import pytest
from gw.scraper import huiji
from gw.scraper.huiji import (
    HUIJI_URL,
    WikitableParser,
    fetch_page,
    fetch_satellite_groups,
    parse_table_by_section,
)


# ---- Sample HTML fixtures ----

SIMPLE_TABLE_HTML = """\
<table class="wikitable">
<tbody>
<tr><th>名称</th><th>数量</th><th>结果</th></tr>
<tr><td>卫星A</td><td>3</td><td>成功</td></tr>
<tr><td>卫星B</td><td>5</td><td>成功</td></tr>
</tbody>
</table>
"""

# Two sections, each with one table
TWO_SECTIONS_HTML = """\
<h2><span class="mw-headline" id="试验星">试验星</span></h2>
<table class="wikitable">
<tbody>
<tr><th>名称</th><th>COSPAR</th></tr>
<tr><td>试验一号</td><td>2023-095</td></tr>
</tbody>
</table>
<h2><span class="mw-headline" id="业务星">业务星</span></h2>
<table class="wikitable">
<tbody>
<tr><th>发射次数</th><th>名称</th><th>COSPAR</th></tr>
<tr><td>1</td><td>高轨01星</td><td>2024-040</td></tr>
<tr><td>2</td><td>低轨01组</td><td>2024-240</td></tr>
</tbody>
</table>
"""

# HTML with links inside cells (like the real wiki)
TABLE_WITH_LINKS_HTML = """\
<h2><span class="mw-headline" id="业务星">业务星</span></h2>
<table class="wikitable">
<tbody>
<tr><th>名称</th><th>研制单位</th></tr>
<tr><td><a href="/wiki/xxx" title="卫星互联网低轨01组A星">卫星互联网低轨01组A星</a>~<a href="/wiki/yyy">K星</a></td><td><a href="/wiki/zzz" title="五院">五院</a></td></tr>
</tbody>
</table>
"""

# HTML with no matching section
NO_MATCH_HTML = """\
<h2><span class="mw-headline" id="其他">其他</span></h2>
<p>no table here</p>
"""

# HTML with section but no table
SECTION_NO_TABLE_HTML = """\
<h2><span class="mw-headline" id="业务星">业务星</span></h2>
<p>no table here</p>
"""

# HTML with section and table with only a header row
EMPTY_TABLE_HTML = """\
<h2><span class="mw-headline" id="业务星">业务星</span></h2>
<table class="wikitable">
<tbody>
<tr><th>名称</th><th>COSPAR</th></tr>
</tbody>
</table>
"""

SHORT_ROW_HTML = """\
<h2><span class="mw-headline" id="业务星">业务星</span></h2>
<table class="wikitable sortable">
<tbody>
<tr><th>名称</th><th>COSPAR</th><th>结果</th></tr>
<tr><td>完整记录</td><td>2024-240</td><td>成功</td></tr>
<tr><td>缺字段记录</td><td>2024-241</td></tr>
<tr><td>额外字段记录</td><td>2024-242</td><td>成功</td><td>备注</td></tr>
</tbody>
</table>
"""


class StubResponse:
    def __init__(self, text="stub html", error=None):
        self.text = text
        self.error = error
        self.raise_for_status_called = False

    def raise_for_status(self):
        self.raise_for_status_called = True
        if self.error is not None:
            raise self.error


class TestWikitableParser:
    def test_parses_simple_table(self):
        parser = WikitableParser()
        parser.feed(SIMPLE_TABLE_HTML)

        assert len(parser.rows) == 3
        assert parser.rows[0] == ["名称", "数量", "结果"]
        assert parser.rows[1] == ["卫星A", "3", "成功"]
        assert parser.rows[2] == ["卫星B", "5", "成功"]

    def test_parses_cells_with_links(self):
        parser = WikitableParser()
        parser.feed(TABLE_WITH_LINKS_HTML)

        # HTMLParser's handle_data is called for text nodes inside <a> tags
        # but our parser only captures handle_data when in_cell is True,
        # so linked text is concatenated
        assert len(parser.rows) >= 2
        # Header row
        assert parser.rows[0] == ["名称", "研制单位"]
        # Data row: text from links is extracted
        data_row = parser.rows[1]
        assert "卫星互联网低轨01组A星" in data_row[0]
        assert "五院" in data_row[1]

    def test_empty_table_produces_header_only(self):
        parser = WikitableParser()
        parser.feed(EMPTY_TABLE_HTML)

        assert len(parser.rows) == 1
        assert parser.rows[0] == ["名称", "COSPAR"]


class TestParseTableBySection:
    def test_extracts_correct_section(self):
        result = parse_table_by_section(TWO_SECTIONS_HTML, "业务星")

        assert len(result) == 2
        assert result[0]["发射次数"] == "1"
        assert result[0]["名称"] == "高轨01星"
        assert result[0]["COSPAR"] == "2024-040"
        assert result[1]["名称"] == "低轨01组"

    def test_extracts_different_section(self):
        result = parse_table_by_section(TWO_SECTIONS_HTML, "试验星")

        assert len(result) == 1
        assert result[0]["名称"] == "试验一号"
        assert result[0]["COSPAR"] == "2023-095"

    def test_raises_on_missing_section(self):
        with pytest.raises(ValueError, match="未找到"):
            parse_table_by_section(NO_MATCH_HTML, "业务星")

    def test_raises_on_missing_table(self):
        with pytest.raises(ValueError, match="未找到"):
            parse_table_by_section(SECTION_NO_TABLE_HTML, "业务星")

    def test_raises_on_empty_table(self):
        with pytest.raises(ValueError, match="数据不足"):
            parse_table_by_section(EMPTY_TABLE_HTML, "业务星")

    def test_extracts_table_with_links(self):
        result = parse_table_by_section(TABLE_WITH_LINKS_HTML, "业务星")

        assert len(result) == 1
        assert "卫星互联网低轨01组A星" in result[0]["名称"]
        assert "五院" in result[0]["研制单位"]

    def test_all_expected_keys_present(self):
        result = parse_table_by_section(TWO_SECTIONS_HTML, "业务星")

        for entry in result:
            assert "发射次数" in entry
            assert "名称" in entry
            assert "COSPAR" in entry

    def test_skips_rows_shorter_than_headers(self):
        result = parse_table_by_section(SHORT_ROW_HTML, "业务星")

        assert result == [
            {"名称": "完整记录", "COSPAR": "2024-240", "结果": "成功"},
            {"名称": "额外字段记录", "COSPAR": "2024-242", "结果": "成功"},
        ]


class TestFetchPage:
    def test_fetches_default_huiji_url_with_browser_impersonation(self, monkeypatch):
        response = StubResponse("<html>星网</html>")
        calls = []

        def fake_get(url, **kwargs):
            calls.append((url, kwargs))
            return response

        monkeypatch.setattr(huiji.requests, "get", fake_get)

        assert fetch_page() == "<html>星网</html>"
        assert calls == [(HUIJI_URL, {"impersonate": "chrome"})]
        assert response.raise_for_status_called

    def test_fetches_custom_url(self, monkeypatch):
        response = StubResponse("custom html")

        def fake_get(url, **kwargs):
            assert url == "https://example.test/wiki"
            assert kwargs == {"impersonate": "chrome"}
            return response

        monkeypatch.setattr(huiji.requests, "get", fake_get)

        assert fetch_page("https://example.test/wiki") == "custom html"

    def test_fetches_page_with_timeout(self, monkeypatch):
        response = StubResponse("custom html")

        def fake_get(url, **kwargs):
            assert url == "https://example.test/wiki"
            assert kwargs == {"impersonate": "chrome", "timeout": 5}
            return response

        monkeypatch.setattr(huiji.requests, "get", fake_get)

        assert fetch_page("https://example.test/wiki", timeout=5) == "custom html"

    def test_raises_http_errors(self, monkeypatch):
        response = StubResponse(error=RuntimeError("bad status"))
        monkeypatch.setattr(huiji.requests, "get", lambda *args, **kwargs: response)

        with pytest.raises(RuntimeError, match="bad status"):
            fetch_page()

        assert response.raise_for_status_called


class TestFetchSatelliteGroups:
    def test_returns_business_satellite_data_from_fetched_html(self, monkeypatch):
        monkeypatch.setattr(huiji, "fetch_page", lambda: TWO_SECTIONS_HTML)

        data = fetch_satellite_groups()

        assert data == [
            {"发射次数": "1", "名称": "高轨01星", "COSPAR": "2024-040"},
            {"发射次数": "2", "名称": "低轨01组", "COSPAR": "2024-240"},
        ]

    def test_propagates_parse_errors(self, monkeypatch):
        monkeypatch.setattr(huiji, "fetch_page", lambda: NO_MATCH_HTML)

        with pytest.raises(ValueError, match="未找到"):
            fetch_satellite_groups()
