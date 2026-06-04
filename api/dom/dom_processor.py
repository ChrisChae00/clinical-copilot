from __future__ import annotations

import html as html_lib
import re
from typing import Any

from bs4 import BeautifulSoup, Comment, Tag
from bs4.element import NavigableString

DROP_TAGS = {
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "canvas",
    "iframe",
    "picture",
    "source",
    "video",
    "audio",
    "object",
    "embed",
    "meta",
    "link",
    "base",
}

DROP_INPUT_TYPES = {
    "hidden",
    "button",
    "submit",
    "reset",
    "image",
    "file",
    "password",
}

CONTROL_CLASS_TOKENS = {
    "dropdown-menu",
    "context-menu",
    "popup-menu",
    "toolbar",
    "button-bar",
    "control-bar",
    "controls",
    "pagination",
    "pager",
    "spinner",
    "loader",
    "loading",
    "tooltip",
    "modal",
    "popover",
    "toast",
}

CONTROL_ROLE_TOKENS = {"menu", "menubar", "toolbar", "tooltip", "dialog", "alertdialog"}

BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "body",
    "caption",
    "dd",
    "details",
    "dialog",
    "div",
    "dl",
    "dt",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "html",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "summary",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
}

CONTAINER_TAGS = {
    "html",
    "body",
    "main",
    "article",
    "section",
    "header",
    "footer",
    "aside",
    "form",
}

MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")

UI_NOISE_EXACT_RE = re.compile(
    r"""
    ^(
        \+|edit|view|print|rev|save|cancel|close|delete|remove|add|update|submit|reset|search|filter|
        loading|working\s*\.\.\.|calendar|browse|expand|collapse|minimize\s+display|toggle\s+print\s+note|
        toggle\s+print|display\s+resolved\s+issues|display\s+unresolved\s+issues|load\s+all\s+notes|
        expand\s+all\s+loaded\s+notes|collapse\s+all\s+loaded\s+notes|browse\s+notes|print\s+dialog
    )$
    """,
    re.I | re.X,
)

UI_PHRASE_RE = re.compile(
    r"\b("
    r"template search|oscar search|ocean toolbar|tools calculators|display resolved issues|display unresolved issues|"
    r"load all notes|expand all loaded notes|collapse all loaded notes|browse notes|research: tools|scratch pad|edit your personal setting"
    r")\b",
    re.I,
)

PLACEHOLDER_VALUE_RE = re.compile(
    r"""
    ^(
        \(?yyyy[-_/ ]?mm[-_/ ]?dd\)?|yyyy-mm-dd|active/resolved/\.\.\.|not\s+set|no\s+yes|
        selected|from\s*:|to\s*:|dates\s+today|assigned\s+issues|insert\s+position|all|none|n/?a|choose|select
    )$
    """,
    re.I | re.X,
)


async def clean_dom(raw_html: str) -> str:
    """
    Convert messy raw HTML into structured, LLM-readable Markdown.

    Fixed behavior:
    - Removes scripts, CSS, hidden fields, images, icons, buttons, links, click handlers, and UI mechanics.
    - Keeps visible page text.
    - Keeps visible link text but removes href/navigation behavior.
    - Keeps plain-text URLs written inside notes.
    - Keeps headings, lists, tables, label/value structure, populated summaries, and active textarea content.
    - Returns Markdown.
    """

    print("dom_processor.clean_dom called with raw_html of length", len(raw_html))

    if not isinstance(raw_html, str) or not raw_html.strip():
        raise ValueError("html must be a non-empty string")

    soup = _sanitize_html(raw_html)
    markdown = _soup_to_markdown(soup)
    cleaned = _postprocess_markdown(markdown)

    if not cleaned.strip():
        raise RuntimeError("DOM cleaner produced empty markdown")

    return cleaned.strip()


def _sanitize_html(raw_html: str) -> BeautifulSoup:
    soup = _parse_html(raw_html)

    _remove_comments(soup)
    _remove_non_content_tags(soup)
    _remove_hidden_elements(soup)
    _remove_popup_and_control_containers(soup)
    _replace_form_controls_with_visible_values(soup)
    _remove_empty_fieldsets(soup)
    _remove_placeholder_only_tables(soup)
    _remove_buttons(soup)
    _remove_images(soup)
    _unwrap_links_keep_visible_text(soup)
    _remove_event_and_style_attributes(soup)
    _replace_label_value_blocks(soup)
    _remove_heading_only_containers(soup)
    _remove_empty_layout_elements(soup)

    return soup


def _parse_html(raw_html: str) -> BeautifulSoup:
    try:
        soup = BeautifulSoup(raw_html, "lxml")
    except Exception:
        soup = BeautifulSoup(raw_html, "html.parser")

    _normalize_bs4_tag_attrs(soup)
    return soup


def _normalize_bs4_tag_attrs(soup: BeautifulSoup) -> None:
    for tag in soup.find_all(True):
        if getattr(tag, "attrs", None) is None:
            tag.attrs = {}


def _is_live_tag(tag: Any) -> bool:
    return (
        isinstance(tag, Tag)
        and tag.name is not None
        and isinstance(getattr(tag, "attrs", None), dict)
    )


def _safe_tag_name(tag: Tag) -> str:
    return str(tag.name).lower() if _is_live_tag(tag) else ""


def _remove_comments(soup: BeautifulSoup) -> None:
    for node in list(soup.find_all(string=lambda value: isinstance(value, Comment))):
        node.extract()


def _remove_non_content_tags(soup: BeautifulSoup) -> None:
    for tag in reversed(list(soup.find_all(True))):
        if _is_live_tag(tag) and _safe_tag_name(tag) in DROP_TAGS:
            tag.decompose()


def _remove_hidden_elements(soup: BeautifulSoup) -> None:
    for tag in reversed(list(soup.find_all(True))):
        if _is_live_tag(tag) and _is_hidden(tag):
            tag.decompose()


def _is_hidden(tag: Tag) -> bool:
    if not _is_live_tag(tag):
        return False

    attrs = tag.attrs

    if "hidden" in attrs:
        return True

    if str(attrs.get("aria-hidden", "")).lower() == "true":
        return True

    style = str(attrs.get("style", ""))
    return bool(re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", style, re.I))


def _remove_popup_and_control_containers(soup: BeautifulSoup) -> None:
    for tag in reversed(list(soup.find_all(True))):
        if _is_live_tag(tag) and _is_popup_or_control_container(tag):
            tag.decompose()


def _is_popup_or_control_container(tag: Tag) -> bool:
    if not _is_live_tag(tag):
        return False

    attrs = tag.attrs

    role = str(attrs.get("role", "")).lower().strip()
    if role in CONTROL_ROLE_TOKENS:
        return True

    raw_classes = attrs.get("class", [])
    if isinstance(raw_classes, str):
        classes = raw_classes.split()
    elif isinstance(raw_classes, (list, tuple, set)):
        classes = [str(c) for c in raw_classes]
    else:
        classes = []

    class_tokens = {c.lower().strip() for c in classes}

    if class_tokens & CONTROL_CLASS_TOKENS:
        return True

    class_text = " ".join(class_tokens)
    element_id = str(attrs.get("id", "")).lower().strip()
    attr_text = f"{element_id} {class_text}"

    if re.search(
        r"(^|[-_\s])(user[-_]?settings|account[-_]?menu|profile[-_]?menu|encounter[-_]?tools|tool[-_]?box|tool[-_]?bar|search[-_]?tools)([-_\s]|$)",
        attr_text,
        re.I,
    ):
        return True

    return bool(
        re.fullmatch(
            r"(menu|popup|tooltip|toolbar|spinner|loader|modal)\d*", element_id
        )
    )


def _replace_form_controls_with_visible_values(soup: BeautifulSoup) -> None:
    for tag in reversed(list(soup.find_all(["textarea", "input", "select"]))):
        if not _is_live_tag(tag):
            continue

        replacement = _visible_form_value(tag, soup)

        if replacement:
            tag.replace_with(NavigableString(f"\n{replacement}\n"))
        else:
            tag.decompose()


def _visible_form_value(tag: Tag, soup: BeautifulSoup) -> str | None:
    if not _is_live_tag(tag):
        return None

    tag_name = _safe_tag_name(tag)
    attrs = tag.attrs

    if tag_name == "textarea":
        value = _normalize_text(
            tag.get_text("\n", strip=True) or attrs.get("value", "")
        )

        if not _meaningful_value(value):
            return None

        return _format_label_value(_find_form_label(tag, soup), value)

    if tag_name == "select":
        values: list[str] = []

        for option in tag.select("option[selected]"):
            value = _normalize_text(option.get_text(" ", strip=True))

            if _meaningful_value(value) and not _placeholder_value(value):
                values.append(value)

        if not values:
            return None

        return _format_label_value(_find_form_label(tag, soup), ", ".join(values))

    if tag_name == "input":
        input_type = str(attrs.get("type", "text")).lower().strip()

        if input_type in DROP_INPUT_TYPES:
            return None

        if input_type in {"checkbox", "radio"}:
            if "checked" not in attrs:
                return None

            label = _find_form_label(tag, soup)
            value = _normalize_text(attrs.get("value", ""))

            if (
                _meaningful_value(value)
                and value.lower() not in {"on", "true"}
                and not _placeholder_value(value)
            ):
                return _format_label_value(label, value)

            return label if _meaningful_value(label) else None

        value = _normalize_text(attrs.get("value", ""))

        if not _meaningful_value(value) or _placeholder_value(value):
            return None

        return _format_label_value(_find_form_label(tag, soup), value)

    return None


def _find_form_label(tag: Tag, soup: BeautifulSoup) -> str:
    if not _is_live_tag(tag):
        return ""

    attrs = tag.attrs

    field_id = attrs.get("id")
    if field_id:
        label = soup.find("label", attrs={"for": field_id})

        if isinstance(label, Tag):
            text = _normalize_text(label.get_text(" ", strip=True))

            if _meaningful_value(text):
                return text

    parent = tag.parent

    if isinstance(parent, Tag) and _safe_tag_name(parent) == "label":
        parent_text = _normalize_text(parent.get_text(" ", strip=True))
        current_value = _normalize_text(attrs.get("value", ""))

        if current_value:
            parent_text = parent_text.replace(current_value, "").strip()

        if _meaningful_value(parent_text):
            return parent_text

    for attr in ("aria-label", "placeholder", "title"):
        value = _normalize_text(attrs.get(attr, ""))

        if _meaningful_value(value) and not _placeholder_value(value):
            return value

    for attr in ("name", "id"):
        value = _normalize_text(attrs.get(attr, ""))

        if _meaningful_value(value):
            return _humanize_identifier(value)

    return ""


def _format_label_value(label: str, value: str) -> str:
    label = _normalize_text(label).strip(" :")
    value = _normalize_text(value)

    if not label:
        return value

    if label.lower() in value.lower()[:120]:
        return value

    return f"{label}: {value}"


def _humanize_identifier(value: str) -> str:
    value = re.sub(r"[_\-]+", " ", str(value))
    value = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)
    return re.sub(r"\s+", " ", value).strip(" :")


def _meaningful_value(value: str) -> bool:
    value = _normalize_text(value)

    if not value or not re.search(r"[A-Za-z0-9]", value):
        return False

    return value.lower() not in {
        "null",
        "undefined",
        "false",
        "off",
        "loading",
        "select",
        "choose",
        "click",
    }


def _placeholder_value(value: str) -> bool:
    value = _normalize_text(value).strip(" :")

    if not value:
        return True

    if PLACEHOLDER_VALUE_RE.match(value):
        return True

    return False


def _remove_empty_fieldsets(soup: BeautifulSoup) -> None:
    for fieldset in reversed(list(soup.find_all("fieldset"))):
        if not _is_live_tag(fieldset):
            continue

        legend = fieldset.find("legend", recursive=False)
        legend_text = (
            _normalize_text(legend.get_text(" ", strip=True))
            if isinstance(legend, Tag)
            else ""
        )
        text = _normalize_text(fieldset.get_text(" ", strip=True))
        remainder = text.replace(legend_text, "", 1).strip() if legend_text else text

        if not remainder or _is_noise_line(remainder):
            fieldset.decompose()


def _remove_placeholder_only_tables(soup: BeautifulSoup) -> None:
    for table in reversed(list(soup.find_all("table"))):
        if not _is_live_tag(table):
            continue

        rows = []

        for tr in table.find_all("tr"):
            cells = [
                _normalize_text(c.get_text(" ", strip=True)).strip()
                for c in tr.find_all(["td", "th"], recursive=False)
            ]

            if any(cells):
                rows.append(cells)

        if not rows:
            continue

        flat = [c.strip(" :") for row in rows for c in row if c.strip()]

        if not flat:
            table.decompose()
            continue

        if _table_has_record_value(table):
            continue

        value_cells = [
            c
            for c in flat
            if not _placeholder_value(c) and not _looks_like_field_label(c)
        ]
        label_cells = [
            c for c in flat if _looks_like_field_label(c) or _placeholder_value(c)
        ]

        if not value_cells and label_cells:
            table.decompose()


def _table_has_record_value(table: Tag) -> bool:
    for cell in table.find_all(["td", "th"]):
        text = _normalize_text(cell.get_text(" ", strip=True)).strip()

        if not text or _placeholder_value(text) or _looks_like_field_label(text):
            continue

        if re.search(r"https?://", text, re.I):
            return True

        if re.search(r"\d{4}-\d{2}-\d{2}|\d{1,2}-[A-Za-z]{3}-\d{4}", text):
            return True

        if re.search(
            r"\b\d+(\.\d+)?\s*(mg|mcg|g|kg|mmhg|bpm|%|mmol|mol|l|ml)\b", text, re.I
        ):
            return True

        if len(text.split()) >= 5 and re.search(r"[.!?]$", text):
            return True

        if not _looks_like_generic_label(text):
            return True

    return False


def _looks_like_field_label(text: str) -> bool:
    text = _normalize_text(text).strip()

    if not text:
        return False

    if text.endswith(":"):
        return True

    if (
        len(text) <= 40
        and len(text.split()) <= 4
        and not re.search(r"\d{4}|https?://|[.!?]$", text, re.I)
    ):
        return True

    return False


def _remove_buttons(soup: BeautifulSoup) -> None:
    for tag in reversed(list(soup.find_all("button"))):
        if _is_live_tag(tag):
            tag.decompose()


def _remove_images(soup: BeautifulSoup) -> None:
    for tag in reversed(list(soup.find_all("img"))):
        if _is_live_tag(tag):
            tag.decompose()


def _unwrap_links_keep_visible_text(soup: BeautifulSoup) -> None:
    for link in reversed(list(soup.find_all("a"))):
        if not _is_live_tag(link):
            continue

        text = _normalize_text(link.get_text(" ", strip=True))

        if not text or UI_NOISE_EXACT_RE.match(text):
            link.decompose()
        else:
            link.unwrap()


def _remove_event_and_style_attributes(soup: BeautifulSoup) -> None:
    for tag in soup.find_all(True):
        if not _is_live_tag(tag):
            continue

        for attr in list(tag.attrs.keys()):
            attr_lower = str(attr).lower()

            if (
                attr_lower == "style"
                or attr_lower.startswith("on")
                or attr_lower in {"href", "src", "target", "rel"}
            ):
                tag.attrs.pop(attr, None)


def _replace_label_value_blocks(soup: BeautifulSoup) -> None:
    for tag in reversed(list(soup.find_all(True))):
        if not _is_live_tag(tag):
            continue

        if _safe_tag_name(tag) not in {"div", "span", "td", "th", "li", "p"}:
            continue

        label_tag = tag.find(class_="label")

        if not isinstance(label_tag, Tag):
            continue

        label = _normalize_text(label_tag.get_text(" ", strip=True)).strip(" :")
        full = _normalize_text(tag.get_text(" ", strip=True))

        if not label or not full:
            continue

        value = full.replace(label, "", 1).strip(" :")

        if not _meaningful_value(value):
            continue

        if len(full) > len(label) + len(value) + 20:
            continue

        tag.clear()
        tag.append(NavigableString(f"{label}: {value}"))


def _remove_heading_only_containers(soup: BeautifulSoup) -> None:
    panel_re = re.compile(r"(box|panel|card|widget|module|section|summary|tile)", re.I)

    for heading in reversed(list(soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]))):
        if not _is_live_tag(heading):
            continue

        if _safe_tag_name(heading) in {"h1", "h2"}:
            continue

        heading_text = _normalize_text(heading.get_text(" ", strip=True))

        if not heading_text:
            heading.decompose()
            continue

        candidate = None
        parent = heading.parent
        depth = 0

        while isinstance(parent, Tag) and depth < 5:
            attrs = (
                getattr(parent, "attrs", {})
                if isinstance(getattr(parent, "attrs", None), dict)
                else {}
            )
            classes = attrs.get("class", [])

            if isinstance(classes, str):
                classes = classes.split()

            attr_text = f"{attrs.get('id', '')} {' '.join(str(c) for c in classes)}"

            if candidate is None and panel_re.search(attr_text):
                candidate = parent

            parent = parent.parent
            depth += 1

        if candidate is None:
            continue

        total_text = _normalize_text(candidate.get_text(" ", strip=True))
        remainder = total_text.replace(heading_text, "", 1).strip()

        if not remainder or _is_noise_line(remainder):
            candidate.decompose()


def _remove_empty_layout_elements(soup: BeautifulSoup) -> None:
    for tag in reversed(list(soup.find_all(True))):
        if not _is_live_tag(tag):
            continue

        tag_name = _safe_tag_name(tag)

        if tag_name in {"br", "hr", "td", "th", "tr", "table"}:
            continue

        text = _normalize_text(tag.get_text(" ", strip=True))

        if text:
            continue

        if tag_name in {
            "div",
            "span",
            "section",
            "article",
            "p",
            "ul",
            "ol",
            "li",
            "form",
            "header",
            "footer",
            "main",
            "aside",
            "fieldset",
        }:
            tag.decompose()


def _soup_to_markdown(soup: BeautifulSoup) -> str:
    root = soup.body if soup.body else soup
    lines = _serialize_children(root)
    return "\n".join(lines)


def _serialize_children(tag: Tag | BeautifulSoup) -> list[str]:
    lines: list[str] = []

    for child in tag.children:
        lines.extend(_serialize_node(child))

    return lines


def _serialize_node(node: Any) -> list[str]:
    if isinstance(node, NavigableString):
        text = _normalize_text(str(node))
        return [text] if text else []

    if not _is_live_tag(node):
        return []

    name = _safe_tag_name(node)

    if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        text = _flatten_text(node)
        return [f"{'#' * int(name[1])} {text}"] if text else []

    if name == "br":
        return []

    if name == "hr":
        return ["---"]

    if name == "table":
        return _table_to_markdown(node)

    if name in {"ul", "ol"}:
        return _list_to_markdown(node, ordered=(name == "ol"))

    if name == "li":
        return _serialize_li(node)

    if name == "pre":
        text = node.get_text("\n", strip=True)
        return ["```", text, "```"] if text else []

    if name in CONTAINER_TAGS or name in {
        "div",
        "p",
        "blockquote",
        "fieldset",
        "details",
        "summary",
        "td",
        "th",
    }:
        child_blocks = [
            child
            for child in node.children
            if isinstance(child, Tag) and _safe_tag_name(child) in BLOCK_TAGS
        ]

        if child_blocks:
            return _serialize_children(node)

        text = _flatten_text(node)

        if not text:
            return []

        if name == "blockquote":
            return [f"> {text}"]

        return [text]

    text = _flatten_text(node)
    return [text] if text else []


def _serialize_li(li: Tag) -> list[str]:
    block_children = [
        child
        for child in li.children
        if isinstance(child, Tag)
        and _safe_tag_name(child)
        in {"ul", "ol", "table", "div", "p", "section", "article"}
    ]

    if not block_children:
        text = _flatten_text(li)
        return [f"- {text}"] if text else []

    direct_text_parts = []

    for child in li.children:
        if isinstance(child, NavigableString):
            text = _normalize_text(str(child))

            if text:
                direct_text_parts.append(text)

        elif isinstance(child, Tag) and _safe_tag_name(child) not in BLOCK_TAGS:
            text = _flatten_text(child)

            if text:
                direct_text_parts.append(text)

    lines = []
    direct = _normalize_text(" ".join(direct_text_parts))

    if direct:
        lines.append(f"- {direct}")

    for child in block_children:
        lines.extend(_serialize_node(child))

    return lines


def _list_to_markdown(tag: Tag, ordered: bool) -> list[str]:
    lines: list[str] = []
    index = 1

    for li in tag.find_all("li", recursive=False):
        item_lines = _serialize_li(li)

        if not item_lines:
            continue

        first = item_lines[0]

        if first.startswith("- ") or re.match(r"^\d+\.\s", first):
            lines.append(
                (f"{index}. " if ordered else "- ") + first[2:]
                if first.startswith("- ")
                else first
            )
        else:
            lines.append(f"{index}. {first}" if ordered else f"- {first}")

        for extra in item_lines[1:]:
            lines.append(extra)

        index += 1

    return lines


def _table_to_markdown(table: Tag) -> list[str]:
    rows: list[list[str]] = []

    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        row = [_flatten_text(cell) for cell in cells]

        if any(row):
            rows.append(row)

    if not rows:
        return []

    max_cols = max(len(row) for row in rows)
    rows = [row + [""] * (max_cols - len(row)) for row in rows]

    if max_cols == 1:
        return [row[0] for row in rows if row[0]]

    output = [
        "| " + " | ".join(rows[0]) + " |",
        "| " + " | ".join(["---"] * max_cols) + " |",
    ]

    for row in rows[1:]:
        output.append("| " + " | ".join(row) + " |")

    return output


def _flatten_text(tag: Tag) -> str:
    return _normalize_text(tag.get_text(" ", strip=True))


def _postprocess_markdown(markdown: str) -> str:
    markdown = html_lib.unescape(markdown)

    lines: list[str] = []

    for raw_line in markdown.splitlines():
        line = _clean_markdown_line(raw_line)

        if not line:
            continue

        if _is_noise_line(line):
            continue

        lines.append(line)

    lines = _collapse_generic_label_value_lines(lines)
    lines = [line for line in lines if not _is_noise_line(line)]
    lines = _remove_empty_label_lines(lines)
    lines = _remove_empty_headings(lines)
    lines = _dedupe_adjacent_lines(lines)

    text = "\n".join(lines)
    text = _remove_repeated_document(text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _clean_markdown_line(line: str) -> str:
    line = str(line or "").replace("\xa0", " ")
    line = MARKDOWN_IMAGE_RE.sub("", line)
    line = MARKDOWN_LINK_RE.sub(r"\1", line)
    line = (
        line.replace("\\(", "(")
        .replace("\\)", ")")
        .replace("\\[", "[")
        .replace("\\]", "]")
    )
    line = re.sub(r"[ \t]+", " ", line).strip()

    if re.fullmatch(r"\|?[\s|]*\|?", line):
        return ""

    plain_table = line.strip().strip("|").strip()

    if (
        plain_table
        and "|" in line
        and all(
            part.strip().strip(":") and set(part.strip().strip(":")) <= {"-"}
            for part in plain_table.split("|")
        )
    ):
        return ""

    return line


def _is_noise_line(line: str) -> bool:
    plain = _plain_text_for_filtering(line)

    if not plain:
        return True

    if "javascript:void" in plain:
        return True

    if UI_NOISE_EXACT_RE.match(plain):
        return True

    if ":" in line:
        _left, _right = line.split(":", 1)

        if _placeholder_value(_right):
            return True

    if len(plain) <= 2 and not any(ch.isalnum() for ch in plain):
        return True

    if (
        len(plain) <= 160
        and UI_PHRASE_RE.search(plain)
        and not _looks_like_record_text(plain)
    ):
        return True

    return False


def _looks_like_record_text(text: str) -> bool:
    text = _normalize_text(text)

    if re.search(r"https?://", text, re.I):
        return True

    if re.search(r"\d{4}-\d{2}-\d{2}", text):
        return True

    if re.search(r"\d{1,2}-[A-Za-z]{3}-\d{4}", text):
        return True

    if re.search(
        r"\b\d+(\.\d+)?\s*(mg|mcg|g|kg|mmhg|bpm|%|mmol|mol|l|ml)\b", text, re.I
    ):
        return True

    if "." in text and len(text.split()) >= 5:
        return True

    if ":" in text and len(text.split()) >= 2 and not _placeholder_value(text):
        return True

    return False


def _plain_text_for_filtering(line: str) -> str:
    text = str(line or "").strip()
    text = re.sub(r"^#{1,6}\s*", "", text)
    text = re.sub(r"^[-*+]\s*", "", text)
    text = text.strip(" |:-")
    return re.sub(r"\s+", " ", text).lower().strip()


def _collapse_generic_label_value_lines(lines: list[str]) -> list[str]:
    collapsed: list[str] = []
    index = 0

    while index < len(lines):
        current = lines[index]

        if index + 1 < len(lines) and _looks_like_generic_label(current):
            next_line = lines[index + 1]

            if _can_be_value_for_label(next_line):
                collapsed.append(f"{current.strip(' :')}: {next_line.strip()}")
                index += 2
                continue

        collapsed.append(current)
        index += 1

    return collapsed


def _looks_like_generic_label(line: str) -> bool:
    if _is_heading(line) or _is_table_line(line):
        return False

    original = str(line or "").strip()

    if re.match(r"^[-*+]\s+", original):
        return False

    text = re.sub(r"^[-*+]\s*", "", original).strip(" :")

    if not text or len(text) > 50 or len(text.split()) > 5:
        return False

    if ":" in text:
        return False

    if re.search(r"[.!?]$|https?://", text, re.I):
        return False

    if "..." in text or "…" in text:
        return False

    if re.search(r"\d{4}-\d{2}-\d{2}|\d{1,2}-[A-Za-z]{3}-\d{4}", text):
        return False

    if re.fullmatch(r"[\d\s:/\-.]+", text):
        return False

    if UI_NOISE_EXACT_RE.match(text):
        return False

    return True


def _can_be_value_for_label(line: str) -> bool:
    if _is_heading(line) or _is_table_line(line):
        return False

    text = str(line or "").strip()

    if not text or _is_noise_line(text):
        return False

    if len(text) > 100:
        return False

    if ":" in text:
        return False

    if len(text.split()) >= 8 and re.search(r"[.!?]$", text):
        return False

    return True


def _remove_empty_label_lines(lines: list[str]) -> list[str]:
    output: list[str] = []

    for i, line in enumerate(lines):
        plain = line.strip()
        normalized = _plain_text_for_filtering(plain)

        if _is_heading(plain) or _is_table_line(plain):
            output.append(line)
            continue

        if re.fullmatch(r"[A-Za-z][A-Za-z0-9 /()_-]{0,40}:?", plain):
            next_line = lines[i + 1] if i + 1 < len(lines) else ""

            if (
                not next_line
                or _is_heading(next_line)
                or _looks_like_generic_label(next_line)
                or _is_table_line(next_line)
                or _is_noise_line(next_line)
            ):
                continue

        if normalized in {"assigned issues", "insert position", "from", "to"}:
            continue

        output.append(line)

    return output


def _remove_empty_headings(lines: list[str]) -> list[str]:
    keep = [True] * len(lines)

    for index, line in enumerate(lines):
        if not _is_heading(line):
            continue

        level = _heading_level(line)
        has_content = False

        for later in lines[index + 1 :]:
            if _is_heading(later) and _heading_level(later) <= level:
                break

            if not _is_heading(later) and not _is_noise_line(later):
                has_content = True
                break

        if not has_content:
            keep[index] = False

    return [line for line, should_keep in zip(lines, keep) if should_keep]


def _dedupe_adjacent_lines(lines: list[str]) -> list[str]:
    output: list[str] = []

    for line in lines:
        if (
            output
            and _normalize_text(line).lower() == _normalize_text(output[-1]).lower()
        ):
            continue

        output.append(line)

    return output


def _remove_repeated_document(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip()]

    if len(lines) < 20:
        return text

    if len(lines) % 2 == 0:
        half = len(lines) // 2

        if lines[:half] == lines[half:]:
            return "\n".join(lines[:half])

    first = lines[0]

    for i in range(10, len(lines)):
        if lines[i] == first:
            before = lines[:i]
            after = lines[i : i + len(before)]

            if before == after:
                return "\n".join(before)

    return text


def _is_heading(line: str) -> bool:
    return bool(re.match(r"^#{1,6}\s+\S", str(line or "").strip()))


def _heading_level(line: str) -> int:
    match = re.match(r"^(#{1,6})\s+", str(line or "").strip())
    return len(match.group(1)) if match else 99


def _is_table_line(line: str) -> bool:
    stripped = str(line or "").strip()
    return stripped.startswith("|") and stripped.endswith("|")


def _normalize_text(text: Any) -> str:
    text = str(text or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


if __name__ == "__main__":
    import asyncio

    with open("tests/testpage1.html", "r", encoding="utf-8") as f:
        test_html = f.read()

    result = asyncio.run(clean_dom(test_html))
    print(result)

    with open("tests/testpage1_cleaned.md", "w", encoding="utf-8") as f:
        f.write(result)
