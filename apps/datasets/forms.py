from django import forms
from django.conf import settings

from apps.ui import apply_bootstrap


def _upload_limit_label() -> str:
    megabytes = max(1, settings.EXCEL_MAX_UPLOAD_BYTES // (1024 * 1024))
    return f"{megabytes} MB"


class UploadForm(forms.Form):
    workbook = forms.FileField(
        help_text=f"Excel .xlsx only, up to {_upload_limit_label()}. Formulas and macros are rejected.",
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        apply_bootstrap(self)

    def clean_workbook(self):
        upload = self.cleaned_data["workbook"]
        if not upload.name.lower().endswith(".xlsx"):
            raise forms.ValidationError(
                "Upload an .xlsx workbook. Macro-enabled files are not accepted."
            )
        if upload.size > settings.EXCEL_MAX_UPLOAD_BYTES:
            raise forms.ValidationError(f"The file exceeds the {_upload_limit_label()} limit.")
        return upload
