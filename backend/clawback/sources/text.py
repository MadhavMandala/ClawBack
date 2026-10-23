"""Email body to plain text, stdlib only (html.parser). Used by the Nylas email source."""

from __future__ import annotations

import re
from html.parser import HTMLParser

_TAG = re.compile(r"<\s*(html|body|div|p|br|table|td|span|a|img|head|meta|style|!doctype)\b", re.I)
_INVISIBLE = re.compile(r"[\u200b-\u200f\u034f\u00ad\u2060\ufeff]")


class _TextOnly(HTMLParser):
    SKIP = {"script", "style", "title", "noscript"}
    BLOCK = {"br", "p", "div", "tr", "li", "ul", "ol", "table", "h1", "h2", "h3", "h4", "h5", "h6",
             "hr", "section", "article", "header", "footer", "blockquote"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skipping += 1
        elif tag in self.BLOCK:
            self.out.append("\n")
        elif tag == "td":
            self.out.append(" ")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skipping = max(0, self.skipping - 1)
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skipping:
            self.out.append(data)


def looks_like_html(text: str) -> bool:
    return bool(_TAG.search(text))


def html_to_text(html: str) -> str:
    if not html:
        return ""
    parser = _TextOnly()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # html.parser is lenient; keep whatever was read
        pass
    return tidy("".join(parser.out))


def tidy(text: str) -> str:
    """Drop invisible padding characters, collapse runs of spaces and blank lines."""
    text = _INVISIBLE.sub("", text).replace("\xa0", " ").replace("\r", "")
    lines: list[str] = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t\f\v]+", " ", line).strip()
        if line or (lines and lines[-1]):
            lines.append(line)
    return "\n".join(lines).strip()


def to_text(body: str) -> str:
    """Body as Nylas returns it (HTML when the message has an HTML part, else plain text) -> plain text."""
    return html_to_text(body) if looks_like_html(body) else tidy(body)
