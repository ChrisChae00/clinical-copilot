from __future__ import annotations

import json
import re
from typing import Any, Iterable

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

NOISE_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "path",
    "link",
    "meta",
    "iframe",
    "object",
}

SECTION_ID_TO_TITLE = {
    "Rx": "Medications",
    "OMeds": "Other Meds",
    "RiskFactors": "Risk Factors",
    "FamHistory": "Family History",
    "allergies": "Allergies",
    "tickler": "Tickler",
    "preventions": "Preventions",
    "Dx": "Disease Registry",
    "unresolvedIssues": "Unresolved Issues",
    "resolvedIssues": "Resolved Issues",
    "Guidelines": "Decision Support Alerts",
    "episode": "Episodes",
    "contacts": "Health Care Team",
    "forms": "Forms",
    "eforms": "eForms",
    "docs": "Documents",
    "labs": "Labs",
    "measurements": "Measurements",
    "consultation": "Consultation",
    "HRM": "HRM",
}

WHITESPACE_RE = re.compile(r"\s+")
DATE_ONLY_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{4}$")


def process_dom(html: str) -> str:
    """
    Convert raw EMR HTML into a compact structured JSON string for the LLM.
    """
    soup = BeautifulSoup(html, "html.parser")

    _remove_noise(soup)

    page_title = (
        _clean_text(soup.title.get_text(" ", strip=True)) if soup.title else None
    )
    patient = _extract_patient_header(soup)
    notes = _extract_encounter_notes(soup)
    sections = _extract_nav_sections(soup)
    generic_fields = _extract_generic_fields(soup, patient)
    free_text_blocks = _extract_free_text_blocks(soup, notes, sections)

    result: dict[str, Any] = {
        "page_title": page_title,
        "page_type": _infer_page_type(page_title, notes, sections, patient),
        "patient": patient,
        "encounter_notes": notes,
        "sections": sections,
        "generic_fields": generic_fields,
        "additional_text": free_text_blocks,
    }

    compact_result = {k: v for k, v in result.items() if _has_meaningful_value(v)}

    return json.dumps(compact_result, ensure_ascii=False, indent=2)


def _remove_noise(soup: BeautifulSoup) -> None:
    for tag_name in NOISE_TAGS:
        for tag in soup.find_all(tag_name):
            if isinstance(tag, Tag):
                tag.decompose()

    if isinstance(soup.head, Tag):
        soup.head.decompose()

    for tag in soup.select(
        "[aria-hidden='true'], [hidden], .oscar-spinner, .oscar-spinner-screen"
    ):
        if isinstance(tag, Tag):
            tag.decompose()

    # Safer than soup.find_all(style=True), because some malformed tags may have attrs=None.
    for tag in soup.find_all(True):
        if not isinstance(tag, Tag):
            continue

        style = _attr_str(_safe_get_attr(tag, "style")).replace(" ", "").lower()
        if "display:none" in style or "visibility:hidden" in style:
            tag.decompose()


def _extract_patient_header(soup: BeautifulSoup) -> dict[str, str]:
    patient: dict[str, str] = {}

    header = soup.find(id="patient-label")
    if not isinstance(header, Tag):
        return patient

    name_node = header.find(id="patient-full-name")
    if isinstance(name_node, Tag):
        patient["name"] = _normalize_person_name(
            _clean_text(name_node.get_text(" ", strip=True))
        )

    for field_id, field_name in [
        ("patient-sex", "sex"),
        ("patient-dob", "dob"),
        ("patient-age", "age"),
        ("patient-phone", "phone"),
        ("patient-mrp", "mrp"),
        ("patient-next-appointment", "next_appointment"),
    ]:
        node = header.find(id=field_id)
        if not isinstance(node, Tag):
            continue

        value = _extract_label_value_from_node(node)
        if value:
            patient[field_name] = value

    return patient


def _extract_encounter_notes(soup: BeautifulSoup) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []

    for note_container in soup.select("div.note, div.encounter-note"):
        if not isinstance(note_container, Tag):
            continue

        text_nodes = note_container.select("div[id^=txt]")
        for text_node in text_nodes:
            if not isinstance(text_node, Tag):
                continue

            text = _clean_multiline_text(text_node.get_text("\n", strip=True))
            if not text:
                continue

            note_data: dict[str, str] = {"text": text}

            text_node_id = _attr_str(_safe_get_attr(text_node, "id"))
            note_id_match = re.search(r"txt(\d+)$", text_node_id)
            if note_id_match:
                note_id = note_id_match.group(1)
                obs = note_container.select_one(f"#obs{note_id}")
                if isinstance(obs, Tag):
                    encounter_date = _clean_text(obs.get_text(" ", strip=True))
                    if encounter_date:
                        note_data["encounter_date"] = encounter_date

            notes.append(note_data)

    return _dedupe_dict_list(notes)


def _extract_nav_sections(soup: BeautifulSoup) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []

    for box in soup.select("div.leftBox"):
        if not isinstance(box, Tag):
            continue

        box_id = _attr_str(_safe_get_attr(box, "id")).strip()
        title = _extract_section_title(box, box_id)
        if not title:
            continue

        items = _extract_section_items(box)

        section_data: dict[str, Any] = {
            "title": title,
            "items": items,
        }
        if box_id:
            section_data["id"] = box_id
        if not items:
            section_data["empty"] = True

        sections.append(section_data)

    return _dedupe_sections(sections)


def _extract_section_title(box: Tag, box_id: str) -> str | None:
    title_node = box.select_one(".nav-menu-title")
    if isinstance(title_node, Tag):
        title = _clean_text(title_node.get_text(" ", strip=True))
        if title:
            return title

    if box_id and box_id in SECTION_ID_TO_TITLE:
        return SECTION_ID_TO_TITLE[box_id]

    return None


def _extract_section_items(box: Tag) -> list[str]:
    items: list[str] = []

    for li in box.select("ul > li"):
        if not isinstance(li, Tag):
            continue

        item = _extract_item_text(li)
        if item:
            items.append(item)

    for node in box.select(".topBox-notes, div[id^=txt]"):
        if not isinstance(node, Tag):
            continue

        text = _clean_multiline_text(node.get_text("\n", strip=True))
        if text:
            items.append(text)

    return _dedupe_preserve_order(
        item for item in items if item and item not in {"…", "..."}
    )


def _extract_item_text(node: Tag) -> str | None:
    text = _clean_multiline_text(node.get_text("\n", strip=True))
    if not text or text == "\xa0":
        return None

    if text.replace("\xa0", "").strip() == "":
        return None

    anchor = node.find("a", title=True)
    if isinstance(anchor, Tag):
        title_text = _clean_text(_attr_str(_safe_get_attr(anchor, "title")))
        visible_text = _clean_text(anchor.get_text(" ", strip=True))
        if title_text and len(title_text) > len(visible_text) + 8:
            return title_text

    lines = [_clean_text(x) for x in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return None

    normalized_lines: list[str] = []
    for line in lines:
        if (
            DATE_ONLY_RE.match(line)
            and normalized_lines
            and line in normalized_lines[0]
        ):
            continue
        normalized_lines.append(line)

    return " | ".join(normalized_lines)


def _extract_generic_fields(
    soup: BeautifulSoup, patient: dict[str, str]
) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for label_node in soup.select(".label"):
        if not isinstance(label_node, Tag):
            continue

        label = _clean_text(label_node.get_text(" ", strip=True)).rstrip(":")
        if not label:
            continue

        parent = label_node.parent
        if not isinstance(parent, Tag):
            continue

        value = _extract_label_value_from_node(parent)
        if not value:
            continue

        label_key = label.lower().replace(" ", "_")
        if label_key in patient and patient[label_key] == value:
            continue

        key = (label.lower(), value)
        if key in seen:
            continue
        seen.add(key)

        fields.append({"label": label, "value": value})

    for tr in soup.select("tr"):
        if not isinstance(tr, Tag):
            continue

        cells = tr.find_all(["th", "td"], recursive=False)
        typed_cells = [cell for cell in cells if isinstance(cell, Tag)]
        if len(typed_cells) != 2:
            continue

        left = _clean_text(typed_cells[0].get_text(" ", strip=True)).rstrip(":")
        right = _clean_text(typed_cells[1].get_text(" ", strip=True))

        if not left or not right:
            continue
        if len(left) > 60:
            continue

        key = (left.lower(), right)
        if key in seen:
            continue
        seen.add(key)

        fields.append({"label": left, "value": right})

    return _dedupe_dict_list(fields)


def _extract_free_text_blocks(
    soup: BeautifulSoup,
    notes: list[dict[str, str]],
    sections: list[dict[str, Any]],
) -> list[str]:
    taken_texts: set[str] = set()

    for note in notes:
        text = note.get("text")
        if text:
            taken_texts.add(text)

    for section in sections:
        items = section.get("items")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, str):
                    taken_texts.add(item)

    blocks: list[str] = []

    main_candidates = soup.select(
        "#encMainDiv, #encMainDivWrapper, #body, body, #header, #navigation-layout"
    )

    for root in main_candidates[:3]:
        if not isinstance(root, Tag):
            continue

        for node in root.find_all(["p", "div", "span", "textarea"], recursive=True):
            if not isinstance(node, Tag):
                continue

            node_id = _attr_str(_safe_get_attr(node, "id"))
            if node_id.startswith(("txt", "sig", "summary", "sumary")):
                continue

            text = _clean_multiline_text(node.get_text("\n", strip=True))
            if not text:
                continue
            if text in taken_texts:
                continue
            if len(text) < 8:
                continue
            if text.count("\n") > 25:
                continue
            if "Add Form" in text and len(text) > 200:
                continue
            if "Loading Notes" in text:
                continue

            blocks.append(text)
            taken_texts.add(text)

            if len(blocks) >= 15:
                return _dedupe_preserve_order(blocks)

    return _dedupe_preserve_order(blocks)


def _infer_page_type(
    page_title: str | None,
    notes: list[dict[str, str]],
    sections: list[dict[str, Any]],
    patient: dict[str, str],
) -> str:
    if page_title and "encounter" in page_title.lower():
        return "encounter"
    if notes:
        return "clinical_notes"
    if patient and sections:
        return "patient_chart"
    if patient:
        return "patient_page"
    return "generic_page"


def _extract_label_value_from_node(node: Tag) -> str:
    parts: list[str] = []

    for child in node.children:
        if isinstance(child, NavigableString):
            text = _clean_text(str(child))
            if text:
                parts.append(text)
            continue

        if not isinstance(child, Tag):
            continue

        classes = _attr_list(_safe_get_attr(child, "class"))
        if "label" in classes:
            continue

        text = _clean_text(child.get_text(" ", strip=True))
        if text:
            parts.append(text)

    return _clean_text(" ".join(parts))


def _normalize_person_name(name: str) -> str:
    if not name:
        return ""

    if "," in name:
        last, first = [part.strip() for part in name.split(",", 1)]
        combined = f"{first} {last}".strip()
    else:
        combined = name.strip()

    normalized_parts: list[str] = []
    for part in combined.split():
        normalized_parts.append(part.capitalize() if part.isupper() else part)

    return " ".join(normalized_parts)


def _safe_get_attr(tag: Tag | None, key: str) -> Any:
    """
    Safe attribute access for BeautifulSoup tags.
    Some malformed tags can have attrs=None, which makes tag.get(...) crash.
    """
    if not isinstance(tag, Tag):
        return None

    attrs = getattr(tag, "attrs", None)
    if not isinstance(attrs, dict):
        return None

    return attrs.get(key)


def _attr_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return " ".join(str(v) for v in value if v is not None).strip()
    if value is None:
        return ""
    return str(value)


def _attr_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def _clean_text(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _clean_multiline_text(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("\r", "\n").replace("\xa0", " ")
    lines = [_clean_text(line) for line in text.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines).strip()


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _dedupe_dict_list(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for item in items:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _dedupe_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_title: dict[str, dict[str, Any]] = {}

    for section in sections:
        title = section.get("title")
        if not isinstance(title, str) or not title:
            continue

        if title not in by_title:
            by_title[title] = section
            continue

        existing_items_raw = by_title[title].get("items", [])
        new_items_raw = section.get("items", [])

        existing_items = [x for x in existing_items_raw if isinstance(x, str)]
        new_items = [x for x in new_items_raw if isinstance(x, str)]

        merged_items = _dedupe_preserve_order(existing_items + new_items)
        by_title[title]["items"] = merged_items
        by_title[title]["empty"] = len(merged_items) == 0

    return list(by_title.values())


def _has_meaningful_value(value: Any) -> bool:
    if value is None:
        return False
    if value == "":
        return False
    if value == []:
        return False
    if value == {}:
        return False
    return True


if __name__ == "__main__":
    test_file = "api\\dom\\test_page2.html"

    with open(test_file, "r", encoding="utf-8") as f:
        html_content = f.read()

    processed = process_dom(html_content)

    with open("api\\dom\\processed.json", "w", encoding="utf-8") as f:
        f.write(processed)
