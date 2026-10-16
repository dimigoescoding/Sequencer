from django import forms
from django.conf import settings

from apps.ui import apply_bootstrap


class UploadForm(forms.Form):
    workbook = forms.FileField(
        help_text="Excel .xlsx only, up to 10 MB. Formulas and macros are rejected.",
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
            raise forms.ValidationError("The file exceeds the 10 MB limit.")
        return upload
