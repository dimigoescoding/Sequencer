"""Small form presentation helpers."""

from django import forms


def apply_bootstrap(form: forms.BaseForm) -> None:
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            css = "form-check-input"
        elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
            css = "form-select"
        elif isinstance(widget, forms.FileInput):
            css = "form-control"
        else:
            css = "form-control"
        existing = widget.attrs.get("class", "")
        widget.attrs["class"] = f"{existing} {css}".strip()
