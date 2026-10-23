"""Email body to plain text, stdlib only (html.parser). Used by the Nylas email source."""

from __future__ import annotations

import re
from html.parser import HTMLParser

_TAG = re.compile(r"<\s*(html|body|div|p|br|table|td|span|a|img|head|meta|style|!doctype)\b", re.I)
_INVISIBLE = re.compile(r"[\u200b-\u200f\u034f\u00ad\u2060\ufeff]")


# Inline styles that hide an element. Hidden text is a common place for instructions aimed at an AI reader, so it is
# kept out of the body a model sees and returned separately for the prompt-injection screen (pipeline/guard.py).
_HIDDEN_STYLE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|mso-hide\s*:\s*all"
    r"|(?:font-size|opacity|max-height)\s*:\s*0(?:\.0+)?(?:px|pt|em|rem|%)?\s*(?:;|!|$)", re.I)
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _TextOnly(HTMLParser):
    SKIP = {"script", "style", "title", "noscript"}
    BLOCK = {"br", "p", "div", "tr", "li", "ul", "ol", "table", "h1", "h2", "h3", "h4", "h5", "h6",
             "hr", "section", "article", "header", "footer", "blockquote"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.hidden: list[str] = []
        self.skipping = 0
        self.open: list[tuple[str, bool]] = []  # open elements, and whether each one hides its content

    def _sink(self) -> list[str]:
        return self.hidden if any(h for _, h in self.open) else self.out

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skipping += 1
            return
        if tag not in _VOID:
            a = dict(attrs)
            self.open.append((tag, "hidden" in a or bool(_HIDDEN_STYLE.search(a.get("style") or ""))))
        if tag in self.BLOCK:
            self._sink().append("\n")
        elif tag == "td":
            self._sink().append(" ")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skipping = max(0, self.skipping - 1)
            return
        if tag in self.BLOCK:
            self._sink().append("\n")
        for i in range(len(self.open) - 1, -1, -1):  # close the nearest open element with this name
            if self.open[i][0] == tag:
                del self.open[i:]
                break

    def handle_data(self, data):
        if not self.skipping:
            self._sink().append(data)


def looks_like_html(text: str) -> bool:
    return bool(_TAG.search(text))


def html_to_parts(html: str) -> tuple[str, str]:
    """(visible text, hidden text) of an HTML body. Hidden = inside an element styled not to show."""
    if not html:
        return "", ""
    parser = _TextOnly()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # html.parser is lenient; keep whatever was read
        pass
    return tidy("".join(parser.out)), tidy("".join(parser.hidden))


def html_to_text(html: str) -> str:
    return html_to_parts(html)[0]


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
    return to_parts(body)[0]


def to_parts(body: str) -> tuple[str, str]:
    """(visible text, hidden text) of a body as Nylas returns it. Plain-text bodies have no hidden part."""
    return html_to_parts(body) if looks_like_html(body) else (tidy(body), "")
