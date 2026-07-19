#!/usr/bin/env python3
import argparse
import base64
import html
import json
import re
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"


class HTMLTextParser(HTMLParser):
    block_tags = {"p", "div", "section", "article", "tr", "table", "ul", "ol"}
    heading_tags = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.href_stack = []

    def push_break(self):
        if self.parts and self.parts[-1] != "\n":
            self.parts.append("\n")

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.block_tags or tag in self.heading_tags:
            self.push_break()
        elif tag == "br":
            self.push_break()
        elif tag == "li":
            self.push_break()
            self.parts.append("- ")
        elif tag in {"td", "th"}:
            self.parts.append(" | ")
        elif tag == "a":
            self.href_stack.append(attrs.get("href", ""))

    def handle_endtag(self, tag):
        if tag in self.block_tags or tag in self.heading_tags or tag == "li":
            self.push_break()
        elif tag == "a" and self.href_stack:
            href = self.href_stack.pop()
            if href and not href.startswith("#"):
                current = "".join(self.parts[-8:])
                if href not in current:
                    self.parts.append(f" ({href})")

    def handle_data(self, data):
        if data:
            self.parts.append(data)

    def text(self):
        raw = "".join(self.parts)
        raw = raw.replace("\xa0", " ")
        lines = []
        for line in raw.splitlines():
            line = re.sub(r"[ \t\r\f\v]+", " ", line).strip()
            if line:
                lines.append(line)
        return "\n".join(lines)


class RichHTMLRenderer(HTMLParser):
    block_tags = {"p", "div", "section", "article"}

    def __init__(self, accent="#cf4520", mode="html"):
        super().__init__(convert_charrefs=True)
        self.accent = accent
        self.mode = mode
        self.parts = []
        self.stack = []

    def append_break(self):
        current = "".join(self.parts)
        if current and not current.endswith(("<br>", "<br/>", "\n")):
            self.parts.append("<br/>" if self.mode == "pdf" else "<br>")

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.block_tags:
            if self.parts:
                self.append_break()
            self.stack.append("")
        elif tag == "br":
            self.append_break()
        elif tag == "li":
            self.append_break()
            self.parts.append("&bull; " if self.mode == "pdf" else "&#8226; ")
            self.stack.append("")
        elif tag in {"strong", "b"}:
            self.parts.append("<b>" if self.mode == "pdf" else "<strong>")
            self.stack.append("b" if self.mode == "pdf" else "strong")
        elif tag in {"em", "i"}:
            self.parts.append("<i>" if self.mode == "pdf" else "<em>")
            self.stack.append("i" if self.mode == "pdf" else "em")
        elif tag == "span" and "color" in attrs.get("style", ""):
            if self.mode == "pdf":
                self.parts.append(f'<font color="{html.escape(self.accent)}">')
                self.stack.append("font")
            else:
                self.parts.append('<span class="accent-text">')
                self.stack.append("span")
        elif tag == "span":
            self.stack.append("")
        elif tag == "a":
            href = attrs.get("href", "")
            if self.mode == "html" and href:
                self.parts.append(f'<a href="{html.escape(href, quote=True)}">')
                self.stack.append("a")
            else:
                self.stack.append("")

    def handle_endtag(self, tag):
        if tag in self.block_tags or tag == "li":
            self.append_break()
            if self.stack:
                self.stack.pop()
        elif tag in {"strong", "b", "em", "i", "span", "a"} and self.stack:
            close = self.stack.pop()
            if close:
                self.parts.append(f"</{close}>")

    def handle_data(self, data):
        if data:
            self.parts.append(html.escape(data).replace("\xa0", " "))

    def rendered(self):
        text = "".join(self.parts).strip()
        text = re.sub(r"(<br/?>\s*){3,}", "<br><br>" if self.mode == "html" else "<br/><br/>", text)
        text = re.sub(r"(<br/?>\s*)+$", "", text)
        return text


def clean_text(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if not value:
        return ""
    if "<" in value and ">" in value:
        parser = HTMLTextParser()
        parser.feed(value)
        value = parser.text()
    else:
        value = html.unescape(value).replace("\xa0", " ")
        value = re.sub(r"[ \t\r\f\v]+", " ", value)
    return value.strip()


def render_rich_html(value, accent="#cf4520"):
    parser = RichHTMLRenderer(accent=accent, mode="html")
    parser.feed(value or "")
    return parser.rendered()


def render_rich_pdf(value, accent="#cf4520"):
    parser = RichHTMLRenderer(accent=accent, mode="pdf")
    parser.feed(value or "")
    return parser.rendered()


def slugify(text):
    slug = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return slug[:80] or "course"


def valid_hex_color(value, fallback="#cf4520"):
    if isinstance(value, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", value.strip()):
        return value.strip()
    return fallback


def lighten_hex(value, amount=0.92):
    value = valid_hex_color(value).lstrip("#")
    rgb = [int(value[i : i + 2], 16) for i in (0, 2, 4)]
    lightened = [round(channel + (255 - channel) * amount) for channel in rgb]
    return "#" + "".join(f"{channel:02x}" for channel in lightened)


def extract_theme(course):
    theme = course.get("theme") if isinstance(course.get("theme"), dict) else {}
    accent = valid_hex_color(theme.get("colorAccent") or course.get("color"))
    return {
        "accent": accent,
        "accent_light": lighten_hex(accent, 0.9),
        "heading_font": clean_text(course.get("headingTypeface")) or "Inter",
        "body_font": clean_text(course.get("bodyTypeface")) or "Inter",
        "ui_font": clean_text(course.get("uiTypeface")) or "Inter",
        "theme_id": clean_text(theme.get("themeId")) or "",
        "lesson_header_style": clean_text(theme.get("lessonHeaderStyle")) or "",
        "button_scheme": clean_text(theme.get("buttonScheme")) or "",
        "block_corners": clean_text(theme.get("blockCorners")) or "",
        "block_padding_top": theme.get("blockPaddingTop"),
        "block_padding_bottom": theme.get("blockPaddingBottom"),
    }


def add_line(lines, text="", prefix=""):
    text = clean_text(text)
    if not text:
        return
    for part in text.splitlines():
        part = part.strip()
        if part:
            lines.append(f"{prefix}{part}")


def semantic_line(kind, text, value=""):
    text = clean_text(text)
    if not text:
        return ""
    text = " ".join(part.strip() for part in text.splitlines() if part.strip())
    value = str(value).replace("|", "/")
    return f"[[{kind}|{value}]] {text}"


def semantic_rich_line(kind, html_text, value=""):
    if not clean_text(html_text):
        return ""
    value = str(value).replace("|", "/")
    payload = base64.urlsafe_b64encode(str(html_text).encode("utf-8")).decode("ascii")
    return f"[[{kind}-rich|{value}]] {payload}"


def semantic_panel_line(variant, title, html_text):
    if not clean_text(title) and not clean_text(html_text):
        return ""
    payload = base64.urlsafe_b64encode(
        json.dumps({"title": title or "", "html": html_text or ""}, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    variant = str(variant or "panel").replace("|", "/")
    return f"[[panel|{variant}]] {payload}"


def parse_semantic_line(line):
    match = re.match(r"^\[\[([a-z0-9_-]+)\|([^\]]*)\]\]\s*(.*)$", line)
    if not match:
        return None
    kind = match.group(1)
    value = match.group(2)
    payload = match.group(3)
    if kind.endswith("-rich"):
        raw = base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")
        return {"kind": kind.removesuffix("-rich"), "value": value, "text": clean_text(raw), "raw_html": raw}
    if kind == "panel":
        raw = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
        title = clean_text(raw.get("title"))
        raw_html = raw.get("html") or ""
        text = clean_text(raw_html)
        return {"kind": "panel", "value": value, "title": title, "text": text, "raw_html": raw_html}
    return {"kind": kind, "value": value, "text": payload}


def media_lines(media):
    lines = []
    if not isinstance(media, dict):
        return lines
    image = media.get("image")
    if isinstance(image, dict):
        add_line(lines, image.get("alt") or image.get("originalUrl") or image.get("key"), "Image: ")
    video = media.get("video")
    if isinstance(video, dict):
        label = video.get("originalUrl") or video.get("url") or video.get("key")
        add_line(lines, label, "Video: ")
        for caption in video.get("captions") or []:
            add_line(lines, caption.get("filename") or caption.get("name"), "Caption file: ")
    embed = media.get("embed")
    if isinstance(embed, dict):
        add_line(lines, embed.get("title"), "Embed: ")
        add_line(lines, embed.get("description"), "Embed description: ")
        add_line(lines, embed.get("src") or embed.get("originalUrl"), "Embed URL: ")
    attachment = media.get("attachment")
    if isinstance(attachment, dict):
        add_line(lines, attachment.get("filename") or attachment.get("originalUrl"), "Attachment: ")
    return lines


def extract_question(question, number=None):
    lines = []
    label = f"Question {number}: " if number is not None else "Question: "
    add_line(lines, question.get("title"), label)
    answers = question.get("answers") or []
    if answers:
        lines.append("Options:")
        for answer in answers:
            title = clean_text(answer.get("title") or answer.get("label") or answer.get("matchTitle"))
            match = clean_text(answer.get("matchTitle"))
            if title and match and match != title:
                lines.append(f"- {title} / {match}")
            elif title:
                lines.append(f"- {title}")
    return lines


def extract_block(block):
    lines = []
    block_type = block.get("type", "")
    variant = block.get("variant", "")
    items = block.get("items") or []

    if block_type == "divider":
        for item in items:
            title = clean_text(item.get("title"))
            if title and title.upper() != "CONTINUE":
                add_line(lines, title)
        return lines

    if block_type in {"text", "list"}:
        for idx, item in enumerate(items, 1):
            heading = item.get("heading")
            paragraph = item.get("paragraph")
            title = item.get("title")
            if heading:
                heading_line = semantic_rich_line("heading", heading)
                if heading_line:
                    lines.append(heading_line)
            if title and block_type == "list":
                add_line(lines, title, "- ")
            if paragraph:
                if block_type == "text" and block.get("family") == "impact":
                    callout = semantic_rich_line("callout", paragraph, variant or "impact")
                    if callout:
                        lines.append(callout)
                elif block_type == "list" and variant == "numbered":
                    numbered = semantic_line("numbered", paragraph, idx)
                    if numbered:
                        lines.append(numbered)
                elif block_type == "list" and variant == "checkboxes":
                    checkbox = semantic_line("checkbox", paragraph)
                    if checkbox:
                        lines.append(checkbox)
                elif block_type == "list" and variant == "bulleted":
                    bullet = semantic_line("bullet", paragraph)
                    if bullet:
                        lines.append(bullet)
                elif block_type == "text":
                    rich = semantic_rich_line("rich", paragraph)
                    if rich:
                        lines.append(rich)
                else:
                    prefix = "- " if block_type == "list" else ""
                    add_line(lines, paragraph, prefix)
        return lines

    if block_type == "multimedia":
        for item in items:
            add_line(lines, item.get("caption"))
            lines.extend(media_lines(item.get("media")))
        return lines

    if block_type == "image":
        add_line(lines, block.get("alt"), "Image: ")
        add_line(lines, block.get("originalUrl") or block.get("src"), "Image source: ")
        for item in items:
            add_line(lines, item.get("caption"))
            add_line(lines, item.get("description"))
        return lines

    if block_type == "interactive":
        label = variant.replace("-", " ").title() if variant else "Interactive"
        useful = []
        if variant == "sorting":
            piles = [clean_text(p.get("title")) for p in block.get("piles") or []]
            cards = [clean_text(i.get("title")) for i in items]
            if any(piles):
                useful.append("Categories: " + "; ".join(p for p in piles if p))
            if any(cards):
                useful.append("Cards: " + "; ".join(c for c in cards if c))
        elif variant in {"button", "button stack"} or block.get("family") == "buttons":
            for item in items:
                button_label = clean_text(item.get("label") or item.get("title") or "Button")
                button = semantic_line("button", button_label)
                if button:
                    useful.append(button)
                desc = clean_text(item.get("description"))
                dest = clean_text(item.get("destination"))
                if desc:
                    useful.append(desc)
                if dest:
                    useful.append(f"Link: {dest}")
        elif variant in {"tabs", "accordion"}:
            for item in items:
                panel = semantic_panel_line(variant, item.get("title") or item.get("label"), item.get("description"))
                if panel:
                    useful.append(panel)
        else:
            for item in items:
                bits = []
                date = clean_text(item.get("date"))
                title = clean_text(item.get("title") or item.get("label"))
                desc = clean_text(item.get("description"))
                dest = clean_text(item.get("destination"))
                if date:
                    bits.append(date)
                if title:
                    bits.append(title)
                if desc:
                    bits.append(desc)
                if dest:
                    bits.append(f"Link: {dest}")
                useful.extend(bits)
                useful.extend(media_lines(item.get("media")))
        if useful and not (variant in {"button", "button stack", "tabs", "accordion"} or block.get("family") == "buttons"):
            lines.append(f"[{label}]")
        lines.extend(useful)
        return lines

    if block_type == "knowledgeCheck":
        if items:
            lines.append("[Knowledge Check]")
        for idx, question in enumerate(items, 1):
            lines.extend(extract_question(question, idx))
        return lines

    if block_type == "DRAW_FROM_QUESTION_BANK":
        title = clean_text(block.get("questionBankTitle") or block.get("title") or "Question Bank")
        draw_count = block.get("drawCount")
        header = f"[Question Bank] {title}"
        if draw_count:
            header += f" (draws {draw_count})"
        lines.append(header)
        for idx, question in enumerate(block.get("questions") or [], 1):
            lines.extend(extract_question(question, idx))
        return lines

    for key in ("heading", "title", "paragraph", "description", "caption", "label"):
        add_line(lines, block.get(key))
    for item in items:
        for key in ("heading", "title", "paragraph", "description", "caption", "label"):
            add_line(lines, item.get(key))
        lines.extend(media_lines(item.get("media")))
    lines.extend(media_lines(block.get("media")))
    return lines


def extract_course(data):
    course = data["course"]
    lessons = []
    for lesson in course.get("lessons") or []:
        lesson_lines = []
        add_line(lesson_lines, lesson.get("description"))
        for block in lesson.get("items") or []:
            block_lines = extract_block(block)
            if block_lines:
                lesson_lines.extend(block_lines)
                lesson_lines.append("")
        while lesson_lines and lesson_lines[-1] == "":
            lesson_lines.pop()
        lessons.append(
            {
                "id": lesson.get("id"),
                "title": clean_text(lesson.get("title")) or "Untitled",
                "type": lesson.get("type") or "",
                "lines": lesson_lines,
            }
        )
    return {
        "title": clean_text(course.get("title")) or "SCORM Course",
        "updated": course.get("contentUpdatedAt") or course.get("updatedAt") or "",
        "theme": extract_theme(course),
        "lessons": lessons,
    }


def markdown_escape(text):
    return text.rstrip()


def write_markdown(extracted, path):
    out = [f"# {markdown_escape(extracted['title'])}", ""]
    if extracted["updated"]:
        out += [f"Source content updated: {extracted['updated']}", ""]
    out += [f"Extracted lesson records: {len(extracted['lessons'])}", ""]
    for idx, lesson in enumerate(extracted["lessons"], 1):
        out += [f"## {idx}. {markdown_escape(lesson['title'])}", ""]
        if lesson["type"]:
            out += [f"_Type: {lesson['type']}._", ""]
        for line in lesson["lines"]:
            semantic = parse_semantic_line(line)
            if not line:
                out.append("")
            elif semantic and semantic["kind"] == "numbered":
                out.append(f"{semantic['value']}. {semantic['text']}")
            elif semantic and semantic["kind"] == "checkbox":
                out.append(f"- [ ] {semantic['text']}")
            elif semantic and semantic["kind"] == "bullet":
                out.append(f"- {semantic['text']}")
            elif semantic and semantic["kind"] == "button":
                out += [f"**Button: {semantic['text']}**", ""]
            elif semantic and semantic["kind"] == "callout":
                out += [f"> {semantic['text']}", ""]
            elif semantic and semantic["kind"] == "heading":
                out += [f"**{semantic['text']}**", ""]
            elif semantic and semantic["kind"] == "rich":
                out += [semantic["text"], ""]
            elif semantic and semantic["kind"] == "panel":
                if semantic["title"]:
                    out += [f"**{semantic['title']}**", ""]
                if semantic["text"]:
                    out += [semantic["text"], ""]
            elif line.startswith("[") and line.endswith("]"):
                out += [f"### {line.strip('[]')}", ""]
            elif line.startswith("- ") or re.match(r"^\d+\. ", line):
                out.append(line)
            elif line.startswith(("Question", "Options:", "Image:", "Video:", "Embed:", "Attachment:", "Caption file:", "Link:", "Categories:", "Cards:")):
                out.append(line)
            else:
                out += [line, ""]
        out.append("")
    path.write_text("\n".join(out).replace("\n\n\n", "\n\n"), encoding="utf-8")


def write_html(extracted, path):
    parts = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'>",
        f"<title>{html.escape(extracted['title'])}</title>",
        "<style>",
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;line-height:1.45;color:#222;margin:0;background:#fff;}",
        "main{max-width:920px;margin:0 auto;padding:40px 32px 80px;}",
        "h1{font-size:30px;margin:0 0 12px;} h2{font-size:22px;margin:34px 0 12px;border-top:1px solid #ddd;padding-top:24px;} h3{font-size:16px;margin:22px 0 8px;color:#6b2737;}",
        "p{margin:8px 0;} .meta{color:#666;font-size:13px;} .line{white-space:pre-wrap;} .aux{color:#444;} @media print{main{max-width:none;padding:0;} h2{break-before:auto;} a{color:#000;}}",
        "</style></head><body><main>",
        f"<h1>{html.escape(extracted['title'])}</h1>",
    ]
    if extracted["updated"]:
        parts.append(f"<p class='meta'>Source content updated: {html.escape(extracted['updated'])}</p>")
    parts.append(f"<p class='meta'>Extracted lesson records: {len(extracted['lessons'])}</p>")
    for idx, lesson in enumerate(extracted["lessons"], 1):
        parts.append(f"<section><h2>{idx}. {html.escape(lesson['title'])}</h2>")
        if lesson["type"]:
            parts.append(f"<p class='meta'>Type: {html.escape(lesson['type'])}</p>")
        for line in lesson["lines"]:
            if not line:
                continue
            semantic = parse_semantic_line(line)
            if semantic and semantic["kind"] == "numbered":
                parts.append(f"<p class='aux line'>{html.escape(semantic['value'])}. {html.escape(semantic['text'])}</p>")
                continue
            if semantic and semantic["kind"] == "checkbox":
                parts.append(f"<p class='aux line'>- {html.escape(semantic['text'])}</p>")
                continue
            if semantic and semantic["kind"] == "bullet":
                parts.append(f"<p class='aux line'>&bull; {html.escape(semantic['text'])}</p>")
                continue
            if semantic and semantic["kind"] == "button":
                parts.append(f"<p class='aux line'>Button: {html.escape(semantic['text'])}</p>")
                continue
            if semantic and semantic["kind"] == "callout":
                parts.append(f"<blockquote>{render_rich_html(semantic['raw_html'])}</blockquote>")
                continue
            if semantic and semantic["kind"] == "heading":
                parts.append(f"<p class='line'><strong>{render_rich_html(semantic['raw_html'])}</strong></p>")
                continue
            if semantic and semantic["kind"] == "rich":
                parts.append(f"<p class='line'>{render_rich_html(semantic['raw_html'])}</p>")
                continue
            if semantic and semantic["kind"] == "panel":
                title = f"<strong>{html.escape(semantic['title'])}</strong><br>" if semantic["title"] else ""
                parts.append(f"<blockquote>{title}{render_rich_html(semantic['raw_html'])}</blockquote>")
                continue
            escaped = html.escape(line)
            if line.startswith("[") and line.endswith("]"):
                parts.append(f"<h3>{html.escape(line.strip('[]'))}</h3>")
            else:
                cls = "aux line" if line.startswith(("Question", "Options:", "-", "Image:", "Video:", "Embed:", "Attachment:", "Caption file:", "Link:", "Categories:", "Cards:")) or re.match(r"^\d+\. ", line) else "line"
                parts.append(f"<p class='{cls}'>{escaped}</p>")
        parts.append("</section>")
    parts.append("</main></body></html>")
    path.write_text("\n".join(parts), encoding="utf-8")


def html_line_class(line):
    semantic = parse_semantic_line(line)
    if semantic:
        return semantic["kind"]
    if line.startswith("[") and line.endswith("]"):
        return "subhead"
    if re.match(r"^Question(?:\s+\d+)?:", line):
        return "question"
    if line == "Options:" or line.startswith("- ") or re.match(r"^\d+\. ", line):
        return "aux listish"
    if line.startswith(("Image:", "Video:", "Embed:", "Attachment:", "Caption file:", "Link:", "Categories:", "Cards:")):
        return "aux resource"
    return "line"


def write_styled_html(extracted, path):
    theme = extracted["theme"]
    accent = theme["accent"]
    accent_light = theme["accent_light"]
    heading_font = html.escape(theme["heading_font"])
    body_font = html.escape(theme["body_font"])
    parts = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'>",
        f"<title>{html.escape(extracted['title'])}</title>",
        "<style>",
        f":root{{--accent:{accent};--accent-light:{accent_light};--ink:#202020;--muted:#6b625e;--panel:#f8f6f4;--rule:#e5dfdb;}}",
        f"body{{font-family:{body_font},-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;line-height:1.55;color:var(--ink);margin:0;background:#fff;}}",
        f"h1,h2,h3{{font-family:{heading_font},-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;letter-spacing:0;}}",
        ".cover{background:linear-gradient(90deg,var(--accent) 0 9px,#3b302b 9px 100%);color:#fff;padding:48px 56px 42px;}",
        ".cover h1{font-size:34px;line-height:1.15;margin:0 0 14px;max-width:980px;}",
        ".cover .meta{color:#f2e8e4;font-size:13px;margin:4px 0;}",
        "main{max-width:930px;margin:0 auto;padding:34px 32px 80px;}",
        "section.lesson{border-top:1px solid var(--rule);padding:30px 0 22px;break-inside:auto;}",
        "section.lesson:first-child{border-top:0;}",
        ".lesson-title{display:grid;grid-template-columns:6px 1fr;gap:16px;align-items:start;margin:0 0 18px;}",
        ".lesson-title:before{content:'';display:block;background:var(--accent);border-radius:4px;height:100%;min-height:38px;}",
        "h2{font-size:24px;line-height:1.25;margin:0;}",
        ".type{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em;margin-top:5px;}",
        "p{margin:9px 0;}",
        ".subhead{background:var(--panel);border-left:4px solid var(--accent);border-radius:8px;padding:9px 12px;margin:20px 0 10px;font-weight:700;color:#3b302b;}",
        ".question{background:var(--accent-light);border:1px solid var(--rule);border-radius:8px;padding:10px 12px;margin-top:16px;font-weight:650;}",
        ".aux{color:#403b38;margin-left:18px;}",
        ".resource{color:#5a514d;font-size:14px;}",
        ".numbered,.checkbox{display:grid;grid-template-columns:34px 1fr;gap:12px;align-items:start;margin:11px 0 11px 24px;color:#403b38;}",
        ".numbered .marker{display:inline-grid;place-items:center;width:28px;height:28px;border-radius:50%;background:var(--accent);color:#fff;font-weight:700;font-size:14px;line-height:1;}",
        ".checkbox .marker{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:5px;border:2px solid var(--accent);color:var(--accent);font-weight:800;font-size:15px;line-height:1;background:#fff;}",
        ".bullet{display:grid;grid-template-columns:18px 1fr;gap:10px;align-items:start;margin:9px 0 9px 28px;color:#403b38;}",
        ".bullet .marker{color:var(--accent);font-size:20px;line-height:1.1;}",
        ".button{display:inline-block;border:2px solid var(--accent);background:var(--accent);color:#fff;border-radius:999px;padding:9px 20px;margin:14px 0 8px;font-weight:700;}",
        ".accent-text{color:var(--accent);font-weight:700;}",
        ".callout{background:var(--panel);border:1px solid var(--rule);border-left:5px solid var(--accent);border-radius:8px;padding:14px 16px;margin:18px 0;}",
        ".callout.definition{font-size:18px;line-height:1.45;}",
        ".callout.note{background:var(--accent-light);}",
        ".inline-heading{font-weight:700;font-size:17px;margin:18px 0 8px;color:#1f1f1f;}",
        ".rich{white-space:normal;}",
        ".panel{border:1px solid var(--rule);border-radius:8px;margin:14px 0;background:#fff;overflow:hidden;}",
        ".panel-title{margin:0;padding:11px 14px;background:var(--panel);border-bottom:1px solid var(--rule);font-weight:700;color:#3b302b;}",
        ".panel-body{padding:13px 14px;}",
        ".panel.accordion{border-left:4px solid var(--accent);}",
        ".panel.tabs{border-top:4px solid var(--accent);}",
        ".section-divider{min-height:280px;display:flex;align-items:center;border-top:0;border-bottom:1px solid var(--rule);}",
        ".section-divider h2{font-size:32px;}",
        ".section-divider .lesson-title{width:100%;}",
        "@media print{.cover{break-after:page;}main{max-width:none;padding:0 12px;}section.lesson{break-before:page;}section.lesson:first-child{break-before:auto;}.section-divider{min-height:0;}.subhead,.question{break-inside:avoid;}}",
        "</style></head><body>",
        "<header class='cover'>",
        f"<h1>{html.escape(extracted['title'])}</h1>",
        f"<p class='meta'>Styled export - extracted lesson records: {len(extracted['lessons'])}</p>",
    ]
    if extracted["updated"]:
        parts.append(f"<p class='meta'>Source content updated: {html.escape(extracted['updated'])}</p>")
    theme_bits = [theme["theme_id"], f"accent {accent}", theme["block_corners"], theme["lesson_header_style"]]
    parts.append(f"<p class='meta'>{html.escape(' | '.join(bit for bit in theme_bits if bit))}</p>")
    parts.append("</header><main>")

    for idx, lesson in enumerate(extracted["lessons"], 1):
        section_class = "lesson section-divider" if lesson["type"] == "section" else "lesson"
        parts.append(f"<section class='{section_class}'>")
        parts.append("<div class='lesson-title'>")
        parts.append("<div>")
        parts.append(f"<h2>{idx}. {html.escape(lesson['title'])}</h2>")
        if lesson["type"]:
            parts.append(f"<div class='type'>{html.escape(lesson['type'])}</div>")
        parts.append("</div></div>")
        for line in lesson["lines"]:
            if not line:
                continue
            cls = html_line_class(line)
            semantic = parse_semantic_line(line)
            if semantic and semantic["kind"] == "numbered":
                parts.append(f"<p class='numbered'><span class='marker'>{html.escape(semantic['value'])}</span><span>{html.escape(semantic['text'])}</span></p>")
            elif semantic and semantic["kind"] == "checkbox":
                parts.append(f"<p class='checkbox'><span class='marker'>&#10003;</span><span>{html.escape(semantic['text'])}</span></p>")
            elif semantic and semantic["kind"] == "bullet":
                parts.append(f"<p class='bullet'><span class='marker'>&#8226;</span><span>{html.escape(semantic['text'])}</span></p>")
            elif semantic and semantic["kind"] == "button":
                parts.append(f"<p><span class='button'>{html.escape(semantic['text'])}</span></p>")
            elif semantic and semantic["kind"] == "callout":
                callout_class = "note" if semantic["value"] == "note" else "definition"
                parts.append(f"<div class='callout {callout_class}'>{render_rich_html(semantic['raw_html'], accent)}</div>")
            elif semantic and semantic["kind"] == "heading":
                parts.append(f"<p class='inline-heading'>{render_rich_html(semantic['raw_html'], accent)}</p>")
            elif semantic and semantic["kind"] == "rich":
                parts.append(f"<p class='line rich'>{render_rich_html(semantic['raw_html'], accent)}</p>")
            elif semantic and semantic["kind"] == "panel":
                title = f"<div class='panel-title'>{html.escape(semantic['title'])}</div>" if semantic["title"] else ""
                parts.append(f"<div class='panel {html.escape(semantic['value'])}'>{title}<div class='panel-body'>{render_rich_html(semantic['raw_html'], accent)}</div></div>")
            if cls == "subhead":
                parts.append(f"<p class='subhead'>{html.escape(line.strip('[]'))}</p>")
            elif not semantic:
                parts.append(f"<p class='{cls}'>{html.escape(line)}</p>")
        parts.append("</section>")
    parts.append("</main></body></html>")
    path.write_text("\n".join(parts), encoding="utf-8")


def register_font():
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        str(ROOT / "fonts" / "DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            pdfmetrics.registerFont(TTFont("CourseSans", candidate))
            return "CourseSans"
    return "Helvetica"


def safe_pdf_text(text):
    return text.replace("\u2018", "'").replace("\u2019", "'")


def write_pdf(extracted, path, styled=False):
    font = register_font()
    theme = extracted.get("theme", {})
    accent = valid_hex_color(theme.get("accent", "#cf4520"))
    accent_light = lighten_hex(accent, 0.9)
    styles = getSampleStyleSheet()
    title_size = 24 if styled else 20
    body_size = 9.4 if styled else 9
    styles.add(ParagraphStyle("CourseTitle", parent=styles["Title"], fontName=font, fontSize=title_size, leading=title_size + 6, alignment=TA_CENTER, spaceAfter=16, textColor=colors.HexColor("#222222")))
    styles.add(ParagraphStyle("CourseMeta", parent=styles["Normal"], fontName=font, fontSize=8, leading=10, textColor=colors.HexColor("#555555"), alignment=TA_CENTER, spaceAfter=10))
    styles.add(ParagraphStyle("LessonTitle", parent=styles["Heading2"], fontName=font, fontSize=16 if styled else 14, leading=20 if styled else 18, spaceBefore=10, spaceAfter=8, keepWithNext=True, textColor=colors.HexColor("#222222")))
    styles.add(ParagraphStyle("SectionTitle", parent=styles["LessonTitle"], fontSize=20, leading=25, alignment=TA_CENTER, textColor=colors.HexColor(accent), spaceBefore=90, spaceAfter=10))
    styles.add(ParagraphStyle("Subhead", parent=styles["Heading3"], fontName=font, fontSize=11, leading=14, textColor=colors.HexColor(accent if styled else "#6b2737"), spaceBefore=8, spaceAfter=4, keepWithNext=True, borderWidth=0.5 if styled else 0, borderColor=colors.HexColor("#e5dfdb"), borderPadding=6 if styled else 0, backColor=colors.HexColor("#f8f6f4") if styled else None))
    styles.add(ParagraphStyle("Question", parent=styles["BodyText"], fontName=font, fontSize=body_size, leading=body_size + 3, alignment=TA_LEFT, spaceBefore=8, spaceAfter=5, borderWidth=0.5, borderColor=colors.HexColor("#e5dfdb"), borderPadding=6, backColor=colors.HexColor(accent_light), textColor=colors.HexColor("#222222")))
    styles.add(ParagraphStyle("BodyCourse", parent=styles["BodyText"], fontName=font, fontSize=body_size, leading=body_size + 3, alignment=TA_LEFT, spaceAfter=4))
    styles.add(ParagraphStyle("Aux", parent=styles["BodyCourse"], leftIndent=12, firstLineIndent=0, textColor=colors.HexColor("#333333")))
    styles.add(ParagraphStyle("Resource", parent=styles["Aux"], fontSize=8.5, leading=11, textColor=colors.HexColor("#5a514d")))
    styles.add(ParagraphStyle("Numbered", parent=styles["Aux"], leftIndent=22, firstLineIndent=-18, spaceBefore=3, spaceAfter=3))
    styles.add(ParagraphStyle("Checkbox", parent=styles["Aux"], leftIndent=22, firstLineIndent=-18, spaceBefore=3, spaceAfter=3))
    styles.add(ParagraphStyle("CourseBullet", parent=styles["Aux"], leftIndent=22, firstLineIndent=-12, spaceBefore=3, spaceAfter=3))
    styles.add(ParagraphStyle("Button", parent=styles["BodyCourse"], fontSize=9.5, leading=12, textColor=colors.HexColor(accent), borderWidth=1, borderColor=colors.HexColor(accent), borderPadding=6, spaceBefore=8, spaceAfter=6))
    styles.add(ParagraphStyle("Callout", parent=styles["BodyCourse"], fontSize=10.2, leading=13.2, borderWidth=0.5, borderColor=colors.HexColor("#e5dfdb"), borderPadding=8, leftIndent=6, rightIndent=6, spaceBefore=8, spaceAfter=8, backColor=colors.HexColor("#f8f6f4")))
    styles.add(ParagraphStyle("Note", parent=styles["Callout"], backColor=colors.HexColor(accent_light)))
    styles.add(ParagraphStyle("InlineHeading", parent=styles["BodyCourse"], fontSize=10.8, leading=13.8, spaceBefore=8, spaceAfter=3, textColor=colors.HexColor("#202020")))
    styles.add(ParagraphStyle("PanelTitle", parent=styles["BodyCourse"], fontSize=10, leading=12.5, textColor=colors.HexColor("#3b302b"), backColor=colors.HexColor("#f8f6f4"), borderWidth=0.5, borderColor=colors.HexColor("#e5dfdb"), borderPadding=6, spaceBefore=8, spaceAfter=0, keepWithNext=True))
    styles.add(ParagraphStyle("PanelBody", parent=styles["BodyCourse"], fontSize=9.2, leading=12.2, borderWidth=0.5, borderColor=colors.HexColor("#e5dfdb"), borderPadding=7, leftIndent=6, rightIndent=6, spaceAfter=7))

    story = [
        Paragraph(html.escape(safe_pdf_text(extracted["title"])), styles["CourseTitle"]),
        Paragraph(html.escape(f"Extracted lesson records: {len(extracted['lessons'])}"), styles["CourseMeta"]),
    ]
    if extracted["updated"]:
        story.append(Paragraph(html.escape(f"Source content updated: {extracted['updated']}"), styles["CourseMeta"]))
    if styled:
        theme_desc = " | ".join(
            bit
            for bit in [
                "Styled export",
                theme.get("theme_id"),
                f"accent {accent}",
                theme.get("block_corners"),
                theme.get("lesson_header_style"),
            ]
            if bit
        )
        story.append(Paragraph(html.escape(theme_desc), styles["CourseMeta"]))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor(accent), spaceBefore=8, spaceAfter=14))
        story.append(PageBreak())
    else:
        story.append(Spacer(1, 0.15 * inch))

    for idx, lesson in enumerate(extracted["lessons"], 1):
        if idx > 1:
            story.append(PageBreak())
        title_style = styles["SectionTitle"] if styled and lesson["type"] == "section" else styles["LessonTitle"]
        story.append(Paragraph(html.escape(safe_pdf_text(f"{idx}. {lesson['title']}")), title_style))
        if lesson["type"]:
            story.append(Paragraph(html.escape(f"Type: {lesson['type']}"), styles["CourseMeta"]))
        if styled and lesson["type"] != "section":
            story.append(HRFlowable(width="100%", thickness=1.3, color=colors.HexColor(accent), spaceBefore=2, spaceAfter=10))
        for line in lesson["lines"]:
            if not line:
                story.append(Spacer(1, 0.05 * inch))
                continue
            semantic = parse_semantic_line(line)
            if semantic and semantic["kind"] == "numbered":
                text = html.escape(safe_pdf_text(semantic["text"]))
                marker = html.escape(semantic["value"])
                story.append(Paragraph(f"<b>{marker}.</b> {text}", styles["Numbered"]))
                continue
            if semantic and semantic["kind"] == "checkbox":
                text = html.escape(safe_pdf_text(semantic["text"]))
                story.append(Paragraph(f"[x] {text}", styles["Checkbox"]))
                continue
            if semantic and semantic["kind"] == "bullet":
                text = html.escape(safe_pdf_text(semantic["text"]))
                story.append(Paragraph(f"&bull; {text}", styles["CourseBullet"]))
                continue
            if semantic and semantic["kind"] == "button":
                text = html.escape(safe_pdf_text(semantic["text"]))
                story.append(Paragraph(f"<b>{text}</b>", styles["Button"]))
                continue
            if semantic and semantic["kind"] == "callout":
                text = render_rich_pdf(semantic["raw_html"], accent)
                callout_style = styles["Note"] if semantic["value"] == "note" else styles["Callout"]
                story.append(Paragraph(text, callout_style))
                continue
            if semantic and semantic["kind"] == "heading":
                text = render_rich_pdf(semantic["raw_html"], accent)
                story.append(Paragraph(f"<b>{text}</b>", styles["InlineHeading"]))
                continue
            if semantic and semantic["kind"] == "rich":
                text = render_rich_pdf(semantic["raw_html"], accent)
                story.append(Paragraph(text, styles["BodyCourse"]))
                continue
            if semantic and semantic["kind"] == "panel":
                if semantic["title"]:
                    story.append(Paragraph(html.escape(safe_pdf_text(semantic["title"])), styles["PanelTitle"]))
                text = render_rich_pdf(semantic["raw_html"], accent)
                if text:
                    story.append(Paragraph(text, styles["PanelBody"]))
                continue
            text = html.escape(safe_pdf_text(line))
            if line.startswith("[") and line.endswith("]"):
                story.append(Paragraph(html.escape(line.strip("[]")), styles["Subhead"]))
            elif styled and re.match(r"^Question(?:\s+\d+)?:", line):
                story.append(Paragraph(text, styles["Question"]))
            elif line.startswith("- "):
                story.append(Paragraph("&bull; " + text[2:], styles["Aux"]))
            elif re.match(r"^\d+\. ", line):
                story.append(Paragraph(text, styles["Aux"]))
            elif styled and line.startswith(("Image:", "Video:", "Embed:", "Attachment:", "Caption file:", "Link:", "Categories:", "Cards:")):
                story.append(Paragraph(text, styles["Resource"]))
            else:
                story.append(Paragraph(text, styles["BodyCourse"]))

    doc = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title=extracted["title"],
    )
    doc.build(story)


def write_report(extracted, path):
    counts = defaultdict(int)
    for lesson in extracted["lessons"]:
        counts[lesson["type"]] += 1
    report = {
        "title": extracted["title"],
        "lesson_records": len(extracted["lessons"]),
        "types": dict(sorted(counts.items())),
        "lessons": [{"index": i + 1, "title": l["title"], "type": l["type"], "line_count": len(l["lines"])} for i, l in enumerate(extracted["lessons"])],
        "note": "Quiz/practice prompts and options are included, but correctness flags and feedback answer-key fields are intentionally omitted.",
    }
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def extract_json_from_payload_text(text):
    patterns = [
        r"__fetchCourse\(\)\s*\{[\s\S]*?deserialize\(\"([A-Za-z0-9+/=]+)\"\)",
        r"deserialize\(\"([A-Za-z0-9+/=]{1000,})\"\)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            import base64

            return base64.b64decode(match.group(1)).decode("utf-8")
    stripped = text.strip()
    if stripped.startswith("{") and '"course"' in stripped:
        return stripped
    raise ValueError("Could not find a SCORM/Rise course payload in the input text.")


def load_course_data(input_json=None, input_payload=None, save_json=None):
    if input_json:
        data = json.loads(Path(input_json).read_text(encoding="utf-8"))
    elif input_payload:
        payload_text = Path(input_payload).read_text(encoding="utf-8")
        json_text = extract_json_from_payload_text(payload_text)
        if save_json:
            Path(save_json).parent.mkdir(parents=True, exist_ok=True)
            Path(save_json).write_text(json_text, encoding="utf-8")
        data = json.loads(json_text)
    else:
        default = ROOT / "work" / "scorm_extract" / "course.json"
        data = json.loads(default.read_text(encoding="utf-8"))
    if "course" not in data:
        raise ValueError("Input JSON does not contain a top-level 'course' object.")
    return data


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export an Articulate Rise/SCORM course package to searchable Markdown, HTML, and PDF."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--input-json", help="Path to a decoded course.json file.")
    source.add_argument("--input-payload", help="Path to text/HTML containing a deserialize(\"base64\") course payload.")
    parser.add_argument("--save-json", help="When using --input-payload, also save the decoded JSON here.")
    parser.add_argument("--output-dir", default=str(OUTPUTS), help="Directory for generated outputs.")
    parser.add_argument("--prefix", help="Filename prefix. Defaults to a slug of the course title.")
    parser.add_argument("--mode", choices=["plain", "styled"], default="plain", help="Export style. 'styled' uses SCORM theme metadata for HTML/PDF.")
    return parser.parse_args()


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    data = load_course_data(args.input_json, args.input_payload, args.save_json)
    extracted = extract_course(data)
    base = slugify(args.prefix or extracted["title"])
    md = output_dir / f"{base}.md"
    html_path = output_dir / f"{base}.html"
    pdf = output_dir / f"{base}.pdf"
    report = output_dir / f"{base}_extraction_report.json"
    write_markdown(extracted, md)
    if args.mode == "styled":
        write_styled_html(extracted, html_path)
    else:
        write_html(extracted, html_path)
    write_pdf(extracted, pdf, styled=args.mode == "styled")
    write_report(extracted, report)
    print(json.dumps({"markdown": str(md), "html": str(html_path), "pdf": str(pdf), "report": str(report), "lesson_records": len(extracted["lessons"]), "mode": args.mode}, indent=2))


if __name__ == "__main__":
    main()
