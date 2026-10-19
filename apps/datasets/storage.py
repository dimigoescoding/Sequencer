"""Store uploaded workbooks in the database.

Render Free web services have an ephemeral disk and cannot attach a persistent
disk. Parsed rows and the original workbook therefore live in Postgres, which
survives spin-down. Object storage can replace this backend later.
"""

from __future__ import annotations

from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class DatabaseStorage(Storage):
    def _open(self, name: str, mode: str = "rb"):
        from apps.datasets.models import StoredFile

        try:
            record = StoredFile.objects.get(path=name)
        except StoredFile.DoesNotExist as exc:
            raise FileNotFoundError(name) from exc
        return ContentFile(bytes(record.content))

    def _save(self, name: str, content) -> str:
        from apps.datasets.models import StoredFile

        data = content.read()
        if isinstance(data, str):
            data = data.encode()
        StoredFile.objects.update_or_create(
            path=name,
            defaults={"content": data, "size": len(data)},
        )
        return name

    def delete(self, name: str) -> None:
        from apps.datasets.models import StoredFile

        StoredFile.objects.filter(path=name).delete()

    def exists(self, name: str) -> bool:
        from apps.datasets.models import StoredFile

        return StoredFile.objects.filter(path=name).exists()

    def size(self, name: str) -> int:
        from apps.datasets.models import StoredFile

        try:
            return StoredFile.objects.get(path=name).size
        except StoredFile.DoesNotExist as exc:
            raise FileNotFoundError(name) from exc

    def url(self, name: str) -> str:
        return ""
