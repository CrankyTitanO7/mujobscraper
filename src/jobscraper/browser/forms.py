"""Extract application questions from static or rendered HTML.

The same extraction runs for saved HTML and for a live Playwright page
(``page.content()``). DOM indices let the filler address controls without
fragile CSS selectors.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field

from bs4 import BeautifulSoup, Tag

from ..models import AnswerKind
from ..utils.matching import normalize_text
from ..utils.text import collapse_whitespace, humanize_identifier

_CONTROL_SELECTOR = "input, textarea, select"
_SKIP_TYPES = {"hidden", "submit", "button", "reset", "image", "search"}
_BOOLEAN_OPTIONS = {
    "yes",
    "no",
    "true",
    "false",
    "y",
    "n",
    "i agree",
    "agree",
    "disagree",
    "authorized",
    "not authorized",
}


@dataclass(slots=True)
class FormField:
    """One question/control group found on an application form."""

    dom_index: int
    field_ref: str
    label: str
    kind: AnswerKind = AnswerKind.FREE_TEXT
    input_type: str = ""
    name: str = ""
    placeholder: str = ""
    required: bool = False
    options: list[str] = dc_field(default_factory=list)
    control_indices: list[int] = dc_field(default_factory=list)
    option_indices: list[int] = dc_field(default_factory=list)

    @property
    def looks_like_resume(self) -> bool:
        text = f"{self.label} {self.name} {self.placeholder}".casefold()
        return any(word in text for word in ("resume", "résumé", "cv", "curriculum vitae"))


def extract_fields_from_html(html: str) -> list[FormField]:
    """Return candidate application questions in document order."""
    soup = BeautifulSoup(html, "html.parser")
    controls = soup.select(_CONTROL_SELECTOR)
    indexed: list[tuple[int, Tag]] = list(enumerate(controls))
    fields: list[FormField] = []
    handled_radio_groups: set[str] = set()

    for dom_index, control in indexed:
        name = str(control.get("name") or "").strip()
        input_type = str(control.get("type") or control.name or "").casefold()
        if control.name == "input" and input_type in _SKIP_TYPES:
            continue
        if control.has_attr("disabled"):
            continue
        if input_type == "radio":
            group_key = name or f"__radio_{dom_index}"
            if group_key in handled_radio_groups:
                continue
            handled_radio_groups.add(group_key)
            group = [
                (index, item)
                for index, item in indexed
                if item.name == "input"
                and str(item.get("type") or "").casefold() == "radio"
                and (str(item.get("name") or "") or f"__radio_{index}") == group_key
            ]
            fields.append(_radio_field(group, soup))
            continue
        if input_type == "checkbox":
            group = [
                (index, item)
                for index, item in indexed
                if item.name == "input"
                and str(item.get("type") or "").casefold() == "checkbox"
                and name
                and str(item.get("name") or "") == name
            ]
            fields.append(_checkbox_field(group or [(dom_index, control)], soup))
            continue
        field = _single_field(dom_index, control)
        if field:
            fields.append(field)
    return _dedupe(fields)


def _is_real_option(text: str) -> bool:
    lowered = text.casefold().strip()
    if not lowered or lowered.startswith(("select", "choose", "--")):
        return False
    return True


def _single_field(dom_index: int, control: Tag) -> FormField | None:
    label = _label_for(control)
    name = str(control.get("name") or control.get("id") or "").strip()
    placeholder = str(control.get("placeholder") or "").strip()
    if not label:
        label = humanize_identifier(placeholder or name)
    if not label:
        return None
    input_type = str(control.get("type") or control.name or "").casefold()
    options: list[str] = []
    if control.name == "select":
        options = [
            collapse_whitespace(option.get_text(" "))
            for option in control.find_all("option")
            if _is_real_option(collapse_whitespace(option.get_text(" ")))
        ]
    kind = _kind_for(input_type, label, options, single=True)
    if control.name == "input" and input_type == "file":
        kind = AnswerKind.FILE
    return FormField(
        dom_index=dom_index,
        field_ref=name or f"field_{dom_index}",
        label=label,
        kind=kind,
        input_type=input_type,
        name=name,
        placeholder=placeholder,
        required=control.has_attr("required") or control.get("aria-required") == "true",
        options=options,
        control_indices=[dom_index],
    )


def _radio_field(group: list[tuple[int, Tag]], soup: BeautifulSoup) -> FormField:
    first = group[0][1]
    name = str(first.get("name") or "").strip()
    labels: list[str] = []
    indices: list[int] = []
    for index, control in group:
        option_label = _label_for(control)
        if not option_label:
            option_label = humanize_identifier(str(control.get("name") or "")) or f"Option {index}"
        labels.append(option_label)
        indices.append(index)
    label = _group_label(first, soup) or humanize_identifier(name) or "Multiple choice"
    kind = (
        AnswerKind.BOOLEAN
        if labels and {normalize_text(item) for item in labels} <= _BOOLEAN_OPTIONS
        else AnswerKind.MULTIPLE_CHOICE
    )
    return FormField(
        dom_index=group[0][0],
        field_ref=name or f"radio_{group[0][0]}",
        label=label,
        kind=kind,
        input_type="radio",
        name=name,
        required=any(control.has_attr("required") for _, control in group),
        options=labels,
        control_indices=[index for index, _ in group],
        option_indices=indices,
    )


def _checkbox_field(group: list[tuple[int, Tag]], soup: BeautifulSoup) -> FormField:
    first = group[0][1]
    name = str(first.get("name") or "").strip()
    labels = [_label_for(control) for _, control in group]
    labels = [label for label in labels if label]
    if len(group) == 1:
        label = labels[0] if labels else _group_label(first, soup) or humanize_identifier(name)
        kind = AnswerKind.BOOLEAN
        options: list[str] = []
    else:
        label = _group_label(first, soup) or humanize_identifier(name) or "Checkboxes"
        kind = AnswerKind.MULTIPLE_CHOICE
        options = labels
    return FormField(
        dom_index=group[0][0],
        field_ref=name or f"checkbox_{group[0][0]}",
        label=label or "Confirmation",
        kind=kind,
        input_type="checkbox",
        name=name,
        required=any(control.has_attr("required") for _, control in group),
        options=options,
        control_indices=[index for index, _ in group],
        option_indices=[index for index, _ in group],
    )


def _kind_for(input_type: str, label: str, options: list[str], *, single: bool) -> AnswerKind:
    if input_type == "file":
        return AnswerKind.FILE
    if input_type == "select" or (input_type in {"radio", "checkbox"} and not single):
        normalized = {normalize_text(item) for item in options}
        if options and normalized <= _BOOLEAN_OPTIONS:
            return AnswerKind.BOOLEAN
        return AnswerKind.MULTIPLE_CHOICE
    if input_type == "checkbox":
        return AnswerKind.BOOLEAN
    return AnswerKind.FREE_TEXT


def _label_for(control: Tag) -> str:
    document = _document(control)
    aria = str(control.get("aria-label") or "").strip()
    if aria:
        return collapse_whitespace(aria)
    labelled_by = str(control.get("aria-labelledby") or "").strip()
    if labelled_by:
        parts = [document.find(id=item) for item in labelled_by.split()]
        text = " ".join(part.get_text(" ") for part in parts if part)
        if text.strip():
            return collapse_whitespace(text)
    control_id = str(control.get("id") or "").strip()
    if control_id:
        label = document.find("label", attrs={"for": control_id})
        if label:
            return collapse_whitespace(label.get_text(" "))
    parent_label = control.find_parent("label")
    if parent_label:
        # The option text is inside the label for radio/checkbox controls.
        text = collapse_whitespace(parent_label.get_text(" "))
        if text:
            return text
    placeholder = collapse_whitespace(str(control.get("placeholder") or ""))
    return placeholder


def _document(node: Tag) -> Tag:
    current = node
    while getattr(current, "parent", None) is not None:
        current = current.parent
    return current


def _group_label(control: Tag, soup: BeautifulSoup) -> str:
    fieldset = control.find_parent("fieldset")
    if fieldset:
        legend = fieldset.find("legend")
        if legend:
            text = collapse_whitespace(legend.get_text(" "))
            if text:
                return text
    # Walk backwards to the nearest short text block before the group.
    node: Tag | None = control
    for _ in range(6):
        node = node.find_previous(["p", "div", "label", "span", "h2", "h3", "h4"])  # type: ignore[assignment]
        if node is None:
            break
        text = collapse_whitespace(node.get_text(" "))
        if 3 <= len(text) <= 300 and not node.find(_CONTROL_SELECTOR):
            return text
    return ""


def _dedupe(fields: list[FormField]) -> list[FormField]:
    seen: set[str] = set()
    result: list[FormField] = []
    for field in fields:
        key = field.field_ref
        if key in seen:
            continue
        seen.add(key)
        result.append(field)
    return sorted(result, key=lambda item: item.dom_index)
