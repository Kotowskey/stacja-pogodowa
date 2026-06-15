import base64
import mimetypes
import re

import markdown
from pathlib import Path
from playwright.sync_api import sync_playwright

CSS_STYLE = """
    @page {
        size: A4;
        margin: 20mm 15mm 20mm 15mm;
        @bottom-right {
            content: counter(page);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            font-size: 9pt;
            color: #6a737d;
        }
    }

    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
        font-size: 11pt;
        line-height: 1.5;
        color: #24292e;
        word-wrap: break-word;
    }

    h1, h2 {
        padding-bottom: 0.3em;
        border-bottom: 1px solid #eaecef;
        color: #24292e;
    }
    h1 { font-size: 22pt; margin-top: 24px; margin-bottom: 16px; font-weight: 600; }
    h2 { font-size: 16pt; margin-top: 24px; margin-bottom: 16px; font-weight: 600; }
    h3 { font-size: 14pt; margin-top: 24px; margin-bottom: 16px; font-weight: 600; }

    h1, h2, h3, h4 { page-break-after: avoid; }

    p { margin-top: 0; margin-bottom: 16px; }

    blockquote {
        padding: 0 1em;
        color: #6a737d;
        border-left: 0.25em solid #dfe2e5;
        margin: 0 0 16px 0;
    }

    ul, ol { padding-left: 2em; margin-top: 0; margin-bottom: 16px; }
    li { margin-top: 0.25em; }

    code {
        padding: 0.2em 0.4em;
        margin: 0;
        font-size: 85%;
        background-color: rgba(27,31,35,0.05);
        border-radius: 3px;
        font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    }

    pre {
        padding: 16px;
        overflow: auto;
        font-size: 85%;
        line-height: 1.45;
        background-color: #f6f8fa;
        border-radius: 3px;
        margin-bottom: 16px;
        page-break-inside: avoid;
    }
    pre code {
        background-color: transparent;
        padding: 0;
        font-size: 100%;
        word-break: normal;
    }

    table {
        display: table;
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 16px;
        page-break-inside: avoid;
    }
    table th, table td {
        padding: 6px 13px;
        border: 1px solid #dfe2e5;
    }
    table tr {
        background-color: #fff;
        border-top: 1px solid #c6cbd1;
    }
    table tr:nth-child(even) {
        background-color: #f6f8fa;
    }

    a {
        color: #0366d6;
        text-decoration: none;
    }

    img {
        max-width: 100%;
        height: auto;
    }

    .strona-tytulowa {
        text-align: center;
        margin-bottom: 24px;
        page-break-after: avoid;
    }

    .strona-tytulowa img {
        display: block;
        margin: 0 auto 24px;
        width: 420px;
        max-width: 90%;
    }

    .strona-tytulowa h1 {
        border-bottom: none;
        font-size: 22pt;
        font-weight: 600;
        margin: 0 0 12px;
    }

    .strona-tytulowa hr {
        width: 45%;
        margin: 16px auto;
        border: none;
        border-top: 1px solid #dfe2e5;
    }

    .strona-tytulowa p {
        margin: 0 0 8px;
        line-height: 1.6;
    }
"""


def osadz_lokalne_obrazy(html: str, katalog_bazowy: Path) -> str:
    def zamien_src(match: re.Match[str]) -> str:
        quote, src = match.group(1), match.group(2)
        if src.startswith(("http://", "https://", "data:", "file:")):
            return match.group(0)

        sciezka_obrazu = (katalog_bazowy / src).resolve()
        if not sciezka_obrazu.is_file():
            return match.group(0)

        typ_mime = mimetypes.guess_type(sciezka_obrazu.name)[0] or "application/octet-stream"
        dane = base64.b64encode(sciezka_obrazu.read_bytes()).decode("ascii")
        return f'src={quote}data:{typ_mime};base64,{dane}{quote}'

    return re.sub(r'src=(["\'])([^"\']+)\1', zamien_src, html)


def konwertuj_md_do_pdf(sciezka_md, sciezka_pdf):
    sciezka_md = Path(sciezka_md).resolve()
    katalog_bazowy = sciezka_md.parent

    with open(sciezka_md, "r", encoding="utf-8") as f:
        tekst_md = f.read()

    html_content = markdown.markdown(tekst_md, extensions=["extra", "toc"])
    html_content = osadz_lokalne_obrazy(html_content, katalog_bazowy)
    full_html = f"""<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="utf-8">
<style>{CSS_STYLE}</style>
</head>
<body>
{html_content}
</body>
</html>"""

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_content(full_html, wait_until="load")
        if page.locator("img").count() > 0:
            page.locator("img").first.wait_for(state="visible", timeout=10000)
        page.pdf(
            path=sciezka_pdf,
            format="A4",
            margin={"top": "20mm", "right": "15mm", "bottom": "20mm", "left": "15mm"},
            print_background=True,
        )
        browser.close()

    print(f"Sukces! PDF zapisany w: {sciezka_pdf}")


if __name__ == "__main__":
    konwertuj_md_do_pdf("README.md", "wynik.pdf")
