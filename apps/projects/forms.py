from django import forms

from apps.projects.models import Project
from apps.ui import apply_bootstrap


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        apply_bootstrap(self)
