from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("optimisation", "0002_programme_packages"),
    ]

    operations = [
        migrations.CreateModel(
            name="RenderPlanState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("desired", models.CharField(default="free", max_length=16)),
                ("error", models.TextField(blank=True)),
            ],
        ),
    ]
