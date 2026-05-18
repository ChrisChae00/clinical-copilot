from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any, Iterable

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

NOISE_TAGS = {
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "path",
    "canvas",
    "iframe",
    "object",
    "embed",
    "audio",
    "video",
    "source",
    "picture",
    "link",
    "meta",
}

SECTION_ID_TO_TITLE = {
    "Rx": "Medications",
    "OMeds": "Other Meds",
    "RiskFactors": "Risk Factors",
    "FamHistory": "Family History",
    "allergies": "Allergies",
    "Allergies": "Allergies",
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
    "msgs": "Messages",
    "pregnancy": "Pregnancy",
}

PATIENT_FIELD_ALIASES = {
    "patient": "name",
    "patient name": "name",
    "name": "name",
    "demographic": "name",
    "sex": "sex",
    "gender": "sex",
    "dob": "dob",
    "date of birth": "dob",
    "birthdate": "dob",
    "age": "age",
    "phone": "phone",
    "home phone": "phone",
    "tel no": "phone",
    "tel.no": "phone",
    "work phone": "work_phone",
    "work no": "work_phone",
    "work no.": "work_phone",
    "cell": "cell_phone",
    "cell no": "cell_phone",
    "cell no.": "cell_phone",
    "email": "email",
    "address": "address",
    "hin": "hin",
    "hin on": "hin",
    "health card": "hin",
    "health card no": "hin",
    "health care #": "hin",
    "health care": "hin",
    "mrp": "mrp",
    "next appt": "next_appointment",
    "next appointment": "next_appointment",
}

BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "dd",
    "details",
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
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}

BUTTON_INPUT_TYPES = {"button", "submit", "reset", "image", "file"}
SKIPPED_INPUT_TYPES = BUTTON_INPUT_TYPES | {"hidden", "password"}
PLACEHOLDER_VALUES = {"", "-", "--", "---", "----", "select", "select type", "default"}
UI_ONLY_TEXT = {
    "+",
    "...",
    "view",
    "edit",
    "print",
    "delete",
    "save",
    "cancel",
    "submit",
    "loading",
    "calendar",
}

WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
DATE_ONLY_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{4}$")
CONTROL_ID_SUFFIX_RE = re.compile(r"[_-]?\d+$")

MAX_ENCOUNTER_NOTES = 40
MAX_SECTIONS = 30
MAX_SECTION_ITEMS = 30
MAX_FORMS = 8
MAX_FORM_FIELDS = 80
MAX_FIELDS = 180
MAX_TABLES = 10
MAX_TABLE_ROWS = 100
MAX_HEADINGS = 40
MAX_LINKS = 40
MAX_ADDITIONAL_TEXT_BLOCKS = 30
MAX_FIELD_VALUE_CHARS = 1500
MAX_TEXT_BLOCK_CHARS = 2200


def process_dom(html: str) -> str:
    """
    Convert raw page HTML into compact JSON text for an LLM.

    The public contract intentionally stays simple: callers pass raw HTML as a
    string and receive a JSON string. The schema is intentionally descriptive,
    not domain-rigid, so OSCAR pages and ordinary web pages both degrade well.
    """
    soup = _parse_html(html or "")
    page_title = _extract_page_title(soup)

    _remove_noise(soup)

    encounter_notes = _extract_encounter_notes(soup)
    forms = _extract_forms(soup)

    # After form extraction, replace visible controls with their selected/value
    # text so table and label/value extraction can read what a person sees.
    _surface_form_values(soup)

    patient = _extract_patient(soup)
    generic_fields = _extract_generic_fields(soup, patient)
    _merge_patient_from_fields(patient, generic_fields)

    sections = _extract_sections(soup)
    tables = _extract_data_tables(soup)
    headings = _extract_headings(soup, patient)
    links = _extract_links(soup)

    taken_texts = _collected_text_signatures(
        patient=patient,
        notes=encounter_notes,
        sections=sections,
        fields=generic_fields,
        forms=forms,
        tables=tables,
        headings=headings,
    )
    additional_text = _extract_additional_text(soup, taken_texts)

    result: dict[str, Any] = {
        "page_title": page_title,
        "page_type": _infer_page_type(
            page_title=page_title,
            patient=patient,
            notes=encounter_notes,
            sections=sections,
            forms=forms,
            fields=generic_fields,
            tables=tables,
            headings=headings,
        ),
        "patient": patient,
        "encounter_notes": encounter_notes,
        "sections": sections,
        "forms": forms,
        "tables": tables,
        "generic_fields": generic_fields,
        "headings": headings,
        "links": links,
        "additional_text": additional_text,
    }

    return json.dumps(_prune_empty(result), ensure_ascii=False, indent=2)


def _parse_html(raw_html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(raw_html, "lxml")
    except Exception:
        return BeautifulSoup(raw_html, "html.parser")


def _extract_page_title(soup: BeautifulSoup) -> str | None:
    if not isinstance(soup.title, Tag):
        return None

    title = _clean_text(soup.title.get_text(" ", strip=True))
    return title or None


def _remove_noise(soup: BeautifulSoup) -> None:
    for tag_name in NOISE_TAGS:
        for tag in list(soup.find_all(tag_name)):
            if isinstance(tag, Tag):
                tag.decompose()

    if isinstance(soup.head, Tag):
        soup.head.decompose()

    selectors = [
        "[aria-hidden='true']",
        "[hidden]",
        ".hidden",
        ".hide",
        ".oscar-spinner",
        ".oscar-spinner-screen",
        ".view-links",
        ".nav-menu-add-button",
        ".glyphicon",
        ".ui-dialog",
        ".calendar-icon",
        "#userSettings",
        "#notesLoading",
    ]
    for tag in list(soup.select(", ".join(selectors))):
        if isinstance(tag, Tag):
            tag.decompose()

    for tag in list(soup.find_all(True)):
        if not isinstance(tag, Tag):
            continue

        if _is_hidden_tag(tag):
            tag.decompose()
            continue

        # Tiny helper links such as lab "info" links and annotation icons add
        # noise without adding clinical content.
        if tag.name == "a" and _is_low_value_link(tag):
            tag.decompose()


def _is_hidden_tag(tag: Tag) -> bool:
    style = _attr_str(_safe_get_attr(tag, "style")).replace(" ", "").lower()
    if "display:none" in style or "visibility:hidden" in style:
        return True

    classes = {item.lower() for item in _attr_list(_safe_get_attr(tag, "class"))}
    return bool(classes & {"hidden", "hide", "sr-only", "visually-hidden"})


def _is_low_value_link(tag: Tag) -> bool:
    text = _clean_text(tag.get_text(" ", strip=True)).lower()
    title = _clean_text(_attr_str(_safe_get_attr(tag, "title"))).lower()
    href = _attr_str(_safe_get_attr(tag, "href")).lower()

    if text in {"info", "...", "+", "view", "edit", "print"} and (
        "javascript:" in href or "medlineplus" in href
    ):
        return True

    if title in {"annotation", "calendar"} and len(text) <= 12:
        return True

    return False


def _extract_patient(soup: BeautifulSoup) -> dict[str, str]:
    patient: dict[str, str] = {}

    header = soup.find(id="patient-label")
    if isinstance(header, Tag):
        name_node = header.find(id="patient-full-name")
        if isinstance(name_node, Tag):
            _set_patient_value(
                patient,
                "name",
                _normalize_person_name(_readable_text(name_node)),
            )

        for node in header.find_all(id=re.compile(r"^patient-")):
            if not isinstance(node, Tag):
                continue

            node_id = _attr_str(_safe_get_attr(node, "id"))
            field_name = node_id.removeprefix("patient-")
            if field_name in {"label", "full-name"}:
                continue

            label_node = node.find(class_="label")
            label = (
                _readable_text(label_node)
                if isinstance(label_node, Tag)
                else _humanize_identifier(field_name)
            )
            patient_key = _patient_key_for_label(label) or _patient_key_for_label(
                field_name
            )
            if not patient_key:
                continue

            value = _extract_label_value_from_node(node)
            if patient_key == "name":
                value = _normalize_person_name(value)
            _set_patient_value(patient, patient_key, value)

    for legend in soup.find_all("legend"):
        if not isinstance(legend, Tag):
            continue

        text = _readable_text(legend)
        match = re.match(r"patient\s*:\s*(.+)$", text, flags=re.IGNORECASE)
        if match:
            _set_patient_value(
                patient,
                "name",
                _normalize_person_name(match.group(1)),
            )

    return patient


def _set_patient_value(patient: dict[str, str], key: str, value: str | None) -> None:
    clean_value = _truncate_text(_clean_multiline_text(value), MAX_FIELD_VALUE_CHARS)
    if not clean_value:
        return

    if key == "name":
        clean_value = _normalize_person_name(clean_value)

    if key not in patient:
        patient[key] = clean_value


def _patient_key_for_label(label: str) -> str | None:
    normalized = _field_key(label)
    return PATIENT_FIELD_ALIASES.get(normalized)


def _merge_patient_from_fields(
    patient: dict[str, str], fields: list[dict[str, str]]
) -> None:
    for field in fields:
        label = field.get("label", "")
        value = field.get("value", "")
        patient_key = _patient_key_for_label(label)
        if patient_key:
            _set_patient_value(patient, patient_key, value)


def _extract_encounter_notes(soup: BeautifulSoup) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []
    seen_text_nodes: set[int] = set()

    for note_container in soup.select("div.note, div.encounter-note"):
        if not isinstance(note_container, Tag):
            continue

        for text_node in note_container.select("div[id^=txt], textarea[id^=txt]"):
            if not isinstance(text_node, Tag):
                continue
            seen_text_nodes.add(id(text_node))
            note = _extract_note_from_text_node(text_node, note_container)
            if note:
                notes.append(note)

    for text_node in soup.select("div[id^=txt]"):
        if not isinstance(text_node, Tag) or id(text_node) in seen_text_nodes:
            continue

        note = _extract_note_from_text_node(text_node, text_node.parent)
        if note:
            notes.append(note)

    return _dedupe_dict_list(notes)[:MAX_ENCOUNTER_NOTES]


def _extract_note_from_text_node(
    text_node: Tag, note_container: Tag | None
) -> dict[str, str] | None:
    text = _truncate_text(
        _clean_multiline_text(text_node.get_text("\n", strip=True)),
        MAX_TEXT_BLOCK_CHARS,
    )
    if not text:
        return None

    note_data: dict[str, str] = {"text": text}
    text_node_id = _attr_str(_safe_get_attr(text_node, "id"))
    note_id_match = re.search(r"txt(\d+)$", text_node_id)

    if note_id_match:
        note_id = note_id_match.group(1)
        note_data["id"] = note_id

        if isinstance(note_container, Tag):
            obs = note_container.select_one(f"#obs{note_id}")
            if isinstance(obs, Tag):
                encounter_date = _clean_text(obs.get_text(" ", strip=True))
                if encounter_date:
                    note_data["encounter_date"] = encounter_date

            enc_type = note_container.select_one(f"#encType{note_id}")
            if isinstance(enc_type, Tag):
                value = _clean_text(enc_type.get_text(" ", strip=True)).strip('"')
                if value:
                    note_data["encounter_type"] = value

            signed = note_container.select_one(f"#signed{note_id}")
            if isinstance(signed, Tag):
                value = _clean_text(_attr_str(_safe_get_attr(signed, "value")))
                if value:
                    note_data["signed"] = value

    return note_data


def _extract_sections(soup: BeautifulSoup) -> list[dict[str, Any]]:
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
            "items": items[:MAX_SECTION_ITEMS],
        }
        if box_id:
            section_data["id"] = box_id
        if not items:
            section_data["empty"] = True

        sections.append(section_data)

    for semantic_section in soup.find_all(["main", "article", "section", "aside"]):
        if not isinstance(semantic_section, Tag):
            continue
        if semantic_section.select_one("div.leftBox"):
            continue

        title = _extract_section_title(semantic_section, "")
        if not title:
            continue

        items = _extract_semantic_section_items(semantic_section)
        if not items:
            continue

        sections.append({"title": title, "items": items[:MAX_SECTION_ITEMS]})

    return _dedupe_sections(sections)[:MAX_SECTIONS]


def _extract_section_title(section: Tag, section_id: str) -> str | None:
    title_node = section.select_one(".nav-menu-title")
    if isinstance(title_node, Tag):
        title = _readable_text(title_node)
        if title:
            return title

    for selector in ["h1", "h2", "h3", "h4", "h5", "h6", "legend"]:
        title_node = section.find(selector)
        if isinstance(title_node, Tag):
            title = _readable_text(title_node)
            if title and _is_meaningful_label(title):
                return title

    aria_label = _clean_text(_attr_str(_safe_get_attr(section, "aria-label")))
    if aria_label:
        return aria_label

    if section_id and section_id in SECTION_ID_TO_TITLE:
        return SECTION_ID_TO_TITLE[section_id]

    return None


def _extract_section_items(section: Tag) -> list[str]:
    items: list[str] = []

    for li in section.select("ul > li, ol > li"):
        if not isinstance(li, Tag):
            continue

        item = _extract_item_text(li)
        if item:
            items.append(item)

    for node in section.select(".topBox-notes, div[id^=txt]"):
        if not isinstance(node, Tag):
            continue

        text = _truncate_text(_clean_multiline_text(_readable_text(node, True)), 800)
        if text:
            items.append(text)

    return _dedupe_preserve_order(
        item for item in items if item and _is_not_ui_only(item)
    )


def _extract_semantic_section_items(section: Tag) -> list[str]:
    title = _extract_section_title(section, "")
    items: list[str] = []

    for node in section.find_all(["p", "li"], recursive=True):
        if not isinstance(node, Tag):
            continue
        if node.find_parent(["main", "article", "section", "aside"]) is not section:
            continue

        text = _truncate_text(_clean_multiline_text(_readable_text(node, True)), 600)
        if text and text != title and _is_not_ui_only(text):
            items.append(text)

    return _dedupe_preserve_order(items)


def _extract_item_text(node: Tag) -> str | None:
    anchor = node.find("a", title=True)
    if isinstance(anchor, Tag):
        title_text = _clean_text(_attr_str(_safe_get_attr(anchor, "title")))
        visible_text = _clean_text(anchor.get_text(" ", strip=True))
        if title_text and len(title_text) > len(visible_text) + 4:
            return title_text

    text = _clean_multiline_text(_readable_text(node, multiline=True))
    if not text or text == "\xa0":
        return None

    lines = [_clean_text(line) for line in text.splitlines()]
    lines = [line for line in lines if line and _is_not_ui_only(line)]
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


def _extract_forms(soup: BeautifulSoup) -> list[dict[str, Any]]:
    forms: list[dict[str, Any]] = []

    for form in soup.find_all("form"):
        if not isinstance(form, Tag) or _is_hidden_tag(form):
            continue

        fields: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()

        for control in form.find_all(["input", "select", "textarea"]):
            if not isinstance(control, Tag) or _is_hidden_tag(control):
                continue

            value = _control_value(control)
            if not value or _is_placeholder_value(value):
                continue

            label = _find_control_label(control, form, soup)
            if not label:
                continue

            field = {
                "label": label,
                "value": _truncate_text(value, MAX_FIELD_VALUE_CHARS),
            }
            key = (_field_key(field["label"]), field["value"])
            if key in seen:
                continue
            seen.add(key)
            fields.append(field)

            if len(fields) >= MAX_FORM_FIELDS:
                break

        if not fields:
            continue

        form_data: dict[str, Any] = {
            "title": _form_title(form),
            "fields": fields,
        }

        form_id = _attr_str(_safe_get_attr(form, "id"))
        form_name = _attr_str(_safe_get_attr(form, "name"))
        if form_id:
            form_data["id"] = form_id
        elif form_name:
            form_data["name"] = form_name

        forms.append(_prune_empty(form_data))
        if len(forms) >= MAX_FORMS:
            break

    return forms


def _form_title(form: Tag) -> str:
    for selector in ["legend", "h1", "h2", "h3", ".title", ".heading"]:
        node = form.find(selector)
        if isinstance(node, Tag):
            text = _readable_text(node)
            if _is_meaningful_label(text):
                return text

    form_id = _attr_str(_safe_get_attr(form, "id"))
    form_name = _attr_str(_safe_get_attr(form, "name"))
    return _humanize_identifier(form_id or form_name or "form")


def _find_control_label(control: Tag, form: Tag, soup: BeautifulSoup) -> str | None:
    for attr_name in ["aria-label", "title", "placeholder"]:
        value = _clean_label(_attr_str(_safe_get_attr(control, attr_name)))
        if value and _is_meaningful_label(value):
            return value

    control_id = _attr_str(_safe_get_attr(control, "id"))
    if control_id:
        label_node = soup.find("label", attrs={"for": control_id})
        if isinstance(label_node, Tag):
            label = _clean_label(label_node.get_text(" ", strip=True))
            if label and _is_meaningful_label(label):
                return label

    parent = control.parent
    if isinstance(parent, Tag) and parent.name == "label":
        parent_text = _clean_label(parent.get_text(" ", strip=True))
        value = _control_value(control)
        label = _remove_value_from_label(parent_text, value)
        if label and _is_meaningful_label(label):
            return label

    row_label = _label_from_table_row(control)
    if row_label:
        return row_label

    previous_label = _label_from_previous_sibling(control)
    if previous_label:
        return previous_label

    name = _attr_str(_safe_get_attr(control, "name"))
    if name:
        return _humanize_identifier(name)

    if control_id:
        return _humanize_identifier(control_id)

    return None


def _label_from_table_row(control: Tag) -> str | None:
    row = control.find_parent("tr")
    if not isinstance(row, Tag):
        return None

    cells = _direct_cells(row)
    if len(cells) < 2:
        return None

    control_cell_index: int | None = None
    for index, cell in enumerate(cells):
        if cell is control or control in cell.descendants:
            control_cell_index = index
            break

    if control_cell_index is None:
        return None

    for cell in reversed(cells[:control_cell_index]):
        label = _clean_label(cell.get_text(" ", strip=True))
        if label and _is_meaningful_label(label):
            return label

    return None


def _label_from_previous_sibling(control: Tag) -> str | None:
    sibling = control.previous_sibling
    while sibling is not None:
        if isinstance(sibling, NavigableString):
            label = _clean_label(str(sibling))
            if label and _is_meaningful_label(label):
                return label
        elif isinstance(sibling, Tag):
            label = _clean_label(sibling.get_text(" ", strip=True))
            if label and _is_meaningful_label(label):
                return label
        sibling = sibling.previous_sibling
    return None


def _control_value(control: Tag) -> str:
    name = control.name.lower() if control.name else ""

    if name == "textarea":
        return _clean_multiline_text(
            control.get_text("\n", strip=True)
            or _attr_str(_safe_get_attr(control, "value"))
        )

    if name == "select":
        selected_options = [
            option
            for option in control.find_all("option")
            if isinstance(option, Tag) and option.has_attr("selected")
        ]
        if not selected_options and control.has_attr("multiple"):
            selected_options = []

        texts = [
            _clean_text(option.get_text(" ", strip=True)) for option in selected_options
        ]
        texts = [text for text in texts if text and not _is_placeholder_value(text)]
        return ", ".join(_dedupe_preserve_order(texts))

    if name != "input":
        return ""

    input_type = _attr_str(_safe_get_attr(control, "type")).lower() or "text"
    if input_type in SKIPPED_INPUT_TYPES:
        return ""

    if input_type in {"checkbox", "radio"}:
        if not control.has_attr("checked"):
            return ""
        value = _clean_text(_attr_str(_safe_get_attr(control, "value")))
        return value if value and value.lower() not in {"on", "true"} else "checked"

    return _clean_text(_attr_str(_safe_get_attr(control, "value")))


def _surface_form_values(soup: BeautifulSoup) -> None:
    for control in list(soup.find_all(["input", "select", "textarea", "button"])):
        if not isinstance(control, Tag):
            continue

        replacement = ""
        if control.name == "button":
            control.decompose()
            continue

        if control.name == "input":
            input_type = _attr_str(_safe_get_attr(control, "type")).lower() or "text"
            if input_type in BUTTON_INPUT_TYPES or input_type in {"hidden", "password"}:
                control.decompose()
                continue
            replacement = _control_value(control)
        else:
            replacement = _control_value(control)

        if replacement:
            control.replace_with(soup.new_string(f" {replacement} "))
        else:
            control.decompose()


def _extract_generic_fields(
    soup: BeautifulSoup, patient: dict[str, str]
) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add_field(label: str, value: str) -> None:
        clean_label = _clean_label(label)
        clean_value = _truncate_text(
            _clean_multiline_text(value), MAX_FIELD_VALUE_CHARS
        )
        if not _should_keep_field(clean_label, clean_value, patient):
            return

        key = (_field_key(clean_label), clean_value)
        if key in seen:
            return
        seen.add(key)
        fields.append({"label": clean_label, "value": clean_value})

    for label_node in soup.select(".label"):
        if not isinstance(label_node, Tag):
            continue

        parent = label_node.parent
        if not isinstance(parent, Tag):
            continue

        label = _clean_label(label_node.get_text(" ", strip=True))
        value = _extract_label_value_from_node(parent)
        add_field(label, value)

    for tr in soup.find_all("tr"):
        if not isinstance(tr, Tag):
            continue

        cells = _direct_cells(tr)
        if len(cells) < 2:
            continue
        if any(cell.find("table") for cell in cells):
            continue

        cell_texts = [
            _clean_multiline_text(_readable_text(cell, multiline=True))
            for cell in cells
        ]
        nonempty_indexes = [
            index for index, cell_text in enumerate(cell_texts) if cell_text
        ]
        if len(nonempty_indexes) < 2:
            continue
        if nonempty_indexes[0] != 0 or nonempty_indexes[1] != 1:
            continue
        if any(cell_texts[index] for index in nonempty_indexes[2:]):
            continue

        left = _clean_label(cell_texts[0])
        right = cell_texts[1]
        add_field(left, right)

    for dt in soup.find_all("dt"):
        if not isinstance(dt, Tag):
            continue

        dd = dt.find_next_sibling("dd")
        if isinstance(dd, Tag):
            add_field(_readable_text(dt), _readable_text(dd, multiline=True))

    for marker in soup.find_all(["strong", "b"]):
        if not isinstance(marker, Tag):
            continue

        label = _clean_label(marker.get_text(" ", strip=True))
        if not label:
            continue

        parent = marker.parent
        if not isinstance(parent, Tag):
            continue

        parent_text = _clean_multiline_text(_readable_text(parent, multiline=True))
        value = _remove_value_from_label(parent_text, label)
        add_field(label, value)

    return fields[:MAX_FIELDS]


def _should_keep_field(
    label: str, value: str, patient: dict[str, str] | None = None
) -> bool:
    if not label or not value:
        return False
    if len(label) > 100:
        return False
    if _field_key(label) in {"nbsp", "n a"}:
        return False
    if _is_not_ui_only(label) is False:
        return False
    if _is_placeholder_value(value):
        return False
    if _field_key(label) == _field_key(value):
        return False
    if "<" in label or ">" in label or "onclick" in label.lower():
        return False
    if value.endswith(":") and len(value.split()) <= 4:
        return False
    if _mostly_option_noise(value):
        return False

    if patient:
        patient_key = _patient_key_for_label(label)
        if patient_key and patient.get(patient_key) == value:
            return False

    return True


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

        classes = {item.lower() for item in _attr_list(_safe_get_attr(child, "class"))}
        if "label" in classes:
            continue

        text = _readable_text(child, multiline=True)
        if text:
            parts.append(text)

    return _clean_multiline_text("\n".join(parts))


def _extract_data_tables(soup: BeautifulSoup) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []

    for table in soup.find_all("table"):
        if not isinstance(table, Tag) or _is_hidden_tag(table):
            continue

        table_data = _extract_one_table(table)
        if table_data:
            tables.append(table_data)
            if len(tables) >= MAX_TABLES:
                break

    return _dedupe_dict_list(tables)


def _extract_one_table(table: Tag) -> dict[str, Any] | None:
    rows = _direct_rows(table)
    if len(rows) < 2:
        return None

    raw_rows: list[list[str]] = []
    row_classes: list[set[str]] = []
    for row in rows:
        cells = _direct_cells(row)
        values = [
            _normalize_table_cell(_readable_text(cell, multiline=True))
            for cell in cells
        ]
        if any(values):
            raw_rows.append(values)
            row_classes.append(
                {item.lower() for item in _attr_list(_safe_get_attr(row, "class"))}
            )

    if len(raw_rows) < 2:
        return None

    header_row_index: int | None = None
    for index, values in enumerate(raw_rows[:3]):
        if _looks_like_header_row(values) and len(values) >= 3:
            header_row_index = index
            break

    if header_row_index is None and not _has_data_row_classes(row_classes):
        return None

    headers: list[str] = []
    data_start = 0
    if header_row_index is not None:
        headers = _unique_headers(raw_rows[header_row_index])
        data_start = header_row_index + 1

    extracted_rows: list[Any] = []
    current_section: str | None = None

    for values in raw_rows[data_start:]:
        nonempty_values = [value for value in values if value]
        if len(nonempty_values) == 1:
            current_section = nonempty_values[0]
            if _is_meaningful_label(current_section):
                extracted_rows.append({"section": current_section})
            continue

        if headers and len(nonempty_values) >= 2:
            row_data: dict[str, str] = {}
            for index, value in enumerate(values):
                header = (
                    headers[index] if index < len(headers) else f"Column {index + 1}"
                )
                row_data[header] = value
            if current_section and "section" not in row_data:
                row_data["section"] = current_section
            if _has_meaningful_value(row_data):
                extracted_rows.append(row_data)
        elif len(nonempty_values) >= 3:
            extracted_rows.append(nonempty_values)

        if len(extracted_rows) >= MAX_TABLE_ROWS:
            break

    data_rows = [
        row
        for row in extracted_rows
        if not (isinstance(row, dict) and set(row.keys()) == {"section"})
    ]
    if not data_rows:
        return None

    if _looks_like_key_value_rows(raw_rows):
        return None

    table_data: dict[str, Any] = {
        "title": _table_title(table),
        "headers": headers,
        "rows": extracted_rows,
    }
    return _prune_empty(table_data)


def _direct_rows(table: Tag) -> list[Tag]:
    return [
        row
        for row in table.find_all("tr")
        if isinstance(row, Tag) and row.find_parent("table") is table
    ]


def _direct_cells(row: Tag) -> list[Tag]:
    return [
        cell
        for cell in row.find_all(["th", "td"], recursive=False)
        if isinstance(cell, Tag)
    ]


def _looks_like_header_row(values: list[str]) -> bool:
    if len(values) < 2:
        return False

    if any(len(value) > 80 for value in values):
        return False

    header_keywords = {
        "test",
        "name",
        "result",
        "abn",
        "reference",
        "range",
        "unit",
        "date",
        "time",
        "status",
        "annotation",
        "type",
        "value",
        "description",
    }
    normalized = {_field_key(value) for value in values}
    return any(
        any(keyword in normalized_value.split() for keyword in header_keywords)
        for normalized_value in normalized
    )


def _has_data_row_classes(row_classes: list[set[str]]) -> bool:
    data_classes = {
        "normalres",
        "abnormalres",
        "correctedres",
        "rollres",
        "abnormalrollres",
        "fielddata",
    }
    return any(classes & data_classes for classes in row_classes)


def _looks_like_key_value_rows(rows: list[list[str]]) -> bool:
    if len(rows) < 3:
        return False

    normalized_rows = [[value for value in row if value] for row in rows]
    two_column_rows = [
        row for row in normalized_rows if len(row) == 2 and len(row[0]) <= 80
    ]
    return len(two_column_rows) / len(rows) > 0.75


def _unique_headers(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []

    for index, header in enumerate(headers):
        clean_header = _clean_label(header) or f"Column {index + 1}"
        count = seen.get(clean_header, 0) + 1
        seen[clean_header] = count
        if count > 1:
            clean_header = f"{clean_header} {count}"
        result.append(clean_header)

    return result


def _table_title(table: Tag) -> str | None:
    caption = table.find("caption", recursive=False)
    if isinstance(caption, Tag):
        title = _readable_text(caption)
        if title:
            return title

    aria_label = _clean_text(_attr_str(_safe_get_attr(table, "aria-label")))
    if aria_label:
        return aria_label

    for sibling in table.previous_siblings:
        if isinstance(sibling, NavigableString):
            if _clean_text(str(sibling)):
                break
            continue

        if not isinstance(sibling, Tag):
            continue

        title_node = sibling.find(
            ["h1", "h2", "h3", "h4", "h5", "h6"],
            class_=False,
        )
        if not isinstance(title_node, Tag):
            title_node = sibling.find(class_=["Title2", "Field2", "heading"])

        if isinstance(title_node, Tag):
            title = _clean_text(title_node.get_text(" ", strip=True))
            if title and len(title) <= 100:
                return title

        sibling_text = _clean_text(sibling.get_text(" ", strip=True))
        if sibling_text and len(sibling_text) <= 80:
            return sibling_text
        break

    table_id = _attr_str(_safe_get_attr(table, "id"))
    if table_id and not CONTROL_ID_SUFFIX_RE.fullmatch(table_id):
        return _humanize_identifier(table_id)

    return None


def _normalize_table_cell(text: str) -> str:
    text = _clean_multiline_text(text)
    if not text:
        return ""

    lines = [line for line in text.splitlines() if _is_not_ui_only(line)]
    text = " ".join(lines)
    text = re.sub(r"\s+\binfo\b$", "", text, flags=re.IGNORECASE)
    return _clean_text(text)


def _extract_headings(soup: BeautifulSoup, patient: dict[str, str]) -> list[str]:
    patient_values = {_text_signature(value) for value in patient.values()}
    headings: list[str] = []

    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "legend"]):
        if not isinstance(heading, Tag):
            continue

        text = _clean_text(heading.get_text(" ", strip=True))
        if not text or not _is_meaningful_label(text):
            continue
        if _text_signature(text) in patient_values:
            continue
        if _text_signature(_normalize_person_name(text)) in patient_values:
            continue

        headings.append(text)

    return _dedupe_preserve_order(headings)[:MAX_HEADINGS]


def _extract_links(soup: BeautifulSoup) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue

        href = _clean_text(_attr_str(_safe_get_attr(anchor, "href")))
        if not href or href.lower().startswith("javascript:") or href == "#":
            continue

        text = _clean_text(anchor.get_text(" ", strip=True))
        title = _clean_text(_attr_str(_safe_get_attr(anchor, "title")))
        label = text or title
        if not label or not _is_not_ui_only(label):
            continue

        link = {"text": _truncate_text(label, 200), "href": href}
        key = (link["text"], link["href"])
        if key in seen:
            continue
        seen.add(key)
        links.append(link)

        if len(links) >= MAX_LINKS:
            break

    return links


def _extract_additional_text(soup: BeautifulSoup, taken_texts: set[str]) -> list[str]:
    blocks: list[str] = []
    seen = set(taken_texts)

    roots = [
        node
        for node in [
            soup.find("main"),
            soup.find("article"),
            soup.find(id="content"),
            soup.find(id="body"),
            soup.body,
        ]
        if isinstance(node, Tag)
    ]
    if not roots:
        roots = [soup]

    for root in roots:
        for node in root.find_all(["p", "li", "div", "td", "pre", "blockquote"]):
            if not isinstance(node, Tag):
                continue
            if not _is_leaf_text_block(node):
                continue

            text = _truncate_text(
                _clean_multiline_text(_readable_text(node, multiline=True)),
                MAX_TEXT_BLOCK_CHARS,
            )
            if not _should_keep_text_block(text):
                continue

            signature = _text_signature(text)
            if signature in seen:
                continue

            blocks.append(text)
            seen.add(signature)

            if len(blocks) >= MAX_ADDITIONAL_TEXT_BLOCKS:
                return blocks

    return blocks


def _is_leaf_text_block(node: Tag) -> bool:
    if _is_hidden_tag(node):
        return False

    nested_blocks = [
        child
        for child in node.find_all(BLOCK_TAGS, recursive=False)
        if isinstance(child, Tag) and child.name not in {"br"}
    ]
    if nested_blocks:
        return False

    return True


def _should_keep_text_block(text: str) -> bool:
    if not text or len(text) < 12:
        return False
    if _is_not_ui_only(text) is False:
        return False
    if _mostly_option_noise(text):
        return False
    if text.count("\n") > 25:
        return False
    if "loading notes" in text.lower():
        return False
    return True


def _collected_text_signatures(
    *,
    patient: dict[str, str],
    notes: list[dict[str, str]],
    sections: list[dict[str, Any]],
    fields: list[dict[str, str]],
    forms: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    headings: list[str],
) -> set[str]:
    signatures: set[str] = set()

    def add(value: Any) -> None:
        if isinstance(value, str):
            signature = _text_signature(value)
            if signature:
                signatures.add(signature)
        elif isinstance(value, dict):
            for child in value.values():
                add(child)
        elif isinstance(value, list):
            for child in value:
                add(child)

    add(patient)
    add(notes)
    add(sections)
    add(fields)
    add(forms)
    add(tables)
    add(headings)
    return signatures


def _infer_page_type(
    *,
    page_title: str | None,
    patient: dict[str, str],
    notes: list[dict[str, str]],
    sections: list[dict[str, Any]],
    forms: list[dict[str, Any]],
    fields: list[dict[str, str]],
    tables: list[dict[str, Any]],
    headings: list[str],
) -> str:
    text = " ".join(
        [
            page_title or "",
            " ".join(headings[:5]),
            " ".join(field.get("label", "") for field in fields[:20]),
        ]
    ).lower()

    if "consult" in text or "referral" in text:
        return "consultation"
    if "document" in text or "uploaded" in text:
        return "document"
    if "lab" in text or any(_table_looks_like_lab(table) for table in tables):
        return "lab_results"
    if page_title and "encounter" in page_title.lower():
        return "encounter"
    if notes:
        return "clinical_notes"
    if patient and sections:
        return "patient_chart"
    if forms:
        return "form_page"
    if tables:
        return "data_page"
    if patient:
        return "patient_page"
    return "generic_page"


def _table_looks_like_lab(table: dict[str, Any]) -> bool:
    headers = " ".join(str(header).lower() for header in table.get("headers", []))
    return "result" in headers and ("reference" in headers or "abn" in headers)


def _readable_text(node: Tag | NavigableString | None, multiline: bool = False) -> str:
    if node is None:
        return ""
    if isinstance(node, NavigableString):
        return _clean_text(str(node))
    if not isinstance(node, Tag):
        return _clean_text(str(node))

    separator = "\n" if multiline else " "
    text = node.get_text(separator, strip=True)
    if multiline:
        return _clean_multiline_text(text)
    return _clean_text(text)


def _remove_value_from_label(text: str, value_or_label: str) -> str:
    text = _clean_multiline_text(text)
    value_or_label = _clean_label(value_or_label)
    if not text or not value_or_label:
        return text

    if text.lower().startswith(value_or_label.lower()):
        remainder = text[len(value_or_label) :]
        return _clean_multiline_text(remainder.lstrip(":").strip())

    return text.replace(value_or_label, "", 1).strip()


def _normalize_person_name(name: str) -> str:
    clean_name = _clean_text(name)
    if not clean_name:
        return ""

    if "," in clean_name:
        last, first = [part.strip() for part in clean_name.split(",", 1)]
        clean_name = f"{first} {last}".strip()

    normalized_parts: list[str] = []
    for part in clean_name.split():
        if part.isupper():
            normalized_parts.append(part.title())
        else:
            normalized_parts.append(part)

    return " ".join(normalized_parts)


def _humanize_identifier(identifier: str) -> str:
    identifier = CONTROL_ID_SUFFIX_RE.sub("", identifier or "")
    identifier = re.sub(r"([a-z])([A-Z])", r"\1 \2", identifier)
    identifier = re.sub(r"[_\-.]+", " ", identifier)
    return _clean_label(identifier).title()


def _field_key(value: str) -> str:
    value = _clean_label(value).lower()
    value = re.sub(r"[^a-z0-9#]+", " ", value)
    return _clean_text(value)


def _clean_label(label: str | None) -> str:
    label = _clean_text(label)
    label = label.rstrip(":")
    label = re.sub(r"\s+", " ", label)
    return label.strip()


def _clean_text(text: str | None) -> str:
    if not text:
        return ""

    text = html_lib.unescape(str(text))
    text = _repair_mojibake(text)
    text = (
        text.replace("\xa0", " ")
        .replace("\u200b", "")
        .replace("\ufeff", "")
        .replace("\r", "\n")
    )
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _clean_multiline_text(text: str | None) -> str:
    if not text:
        return ""

    text = html_lib.unescape(str(text)).replace("\r", "\n")
    text = _repair_mojibake(text)
    text = text.replace("\xa0", " ").replace("\u200b", "").replace("\ufeff", "")
    lines = [_clean_text(line) for line in text.split("\n")]
    lines = [line for line in lines if line]
    return MULTI_NEWLINE_RE.sub("\n\n", "\n".join(lines)).strip()


def _repair_mojibake(text: str) -> str:
    markers = (
        "\u00c2",
        "\u00c3",
        "\u00e2\u20ac",
        "\u00e2\u20ac\u2122",
        "\u00e2\u20ac\u0153",
        "\u00e2\u20ac\u009d",
    )
    if not any(marker in text for marker in markers):
        return text

    repaired = text
    for _ in range(2):
        try:
            candidate = repaired.encode("latin-1").decode("utf-8")
        except UnicodeError:
            break
        if _mojibake_score(candidate) < _mojibake_score(repaired):
            repaired = candidate
        else:
            break

    replacements = {
        "\u00e2\u20ac\u00a6": "...",
        "\u00e2\u20ac\u201c": "-",
        "\u00e2\u20ac\u201d": "-",
        "\u00e2\u20ac\u02dc": "'",
        "\u00e2\u20ac\u2122": "'",
        "\u00e2\u20ac\u0153": '"',
        "\u00e2\u20ac\u009d": '"',
        "\u00c2\u00b0": "deg",
        "\u00c2 ": " ",
    }
    for bad, good in replacements.items():
        repaired = repaired.replace(bad, good)
    return repaired


def _mojibake_score(text: str) -> int:
    return sum(
        text.count(marker)
        for marker in (
            "\u00c2",
            "\u00c3",
            "\u00e2\u20ac",
            "\u00e2\u20ac\u2122",
            "\u00e2\u20ac\u0153",
            "\u00e2\u20ac\u009d",
        )
    )


def _truncate_text(text: str, max_chars: int) -> str:
    text = _clean_multiline_text(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 14].rstrip() + " [truncated]"


def _is_placeholder_value(value: str) -> bool:
    normalized = _clean_text(value).strip().lower()
    if normalized in PLACEHOLDER_VALUES:
        return True
    if normalized.strip("- ") == "":
        return True
    if normalized.startswith("----") and normalized.endswith("----"):
        return True
    return False


def _is_meaningful_label(text: str) -> bool:
    text = _clean_text(text)
    if not text or len(text) > 160:
        return False
    if "<" in text or ">" in text or "onclick" in text.lower():
        return False
    return _is_not_ui_only(text)


def _is_not_ui_only(text: str) -> bool:
    normalized = _field_key(text)
    if normalized in UI_ONLY_TEXT:
        return False
    if normalized.replace(" ", "") in UI_ONLY_TEXT:
        return False
    return True


def _mostly_option_noise(text: str) -> bool:
    if len(text) < 250:
        return False

    words = text.split()
    if not words:
        return False

    unique_words = set(words)
    if len(words) > 80 and len(unique_words) / len(words) < 0.25:
        return True

    return text.count("Select") > 8 or text.count("option") > 8


def _text_signature(text: str) -> str:
    return _field_key(text)


def _safe_get_attr(tag: Tag | None, key: str) -> Any:
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


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        signature = _text_signature(value)
        if not signature or signature in seen:
            continue
        seen.add(signature)
        out.append(value)
    return out


def _dedupe_dict_list(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
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

        title_key = _field_key(title)
        if title_key not in by_title:
            by_title[title_key] = section
            continue

        existing_items_raw = by_title[title_key].get("items", [])
        new_items_raw = section.get("items", [])

        existing_items = [x for x in existing_items_raw if isinstance(x, str)]
        new_items = [x for x in new_items_raw if isinstance(x, str)]

        merged_items = _dedupe_preserve_order(existing_items + new_items)
        by_title[title_key]["items"] = merged_items[:MAX_SECTION_ITEMS]
        by_title[title_key]["empty"] = len(merged_items) == 0

    return list(by_title.values())


def _prune_empty(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: pruned
            for key, child in value.items()
            if _has_meaningful_value(pruned := _prune_empty(child))
        }

    if isinstance(value, list):
        return [
            pruned
            for child in value
            if _has_meaningful_value(pruned := _prune_empty(child))
        ]

    return value


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
