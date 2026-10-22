from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("scenarios", "0003_workbook_catalogue"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="vesselsettings",
            name="solver_time_limit_at_most_30",
        ),
        migrations.AddConstraint(
            model_name="vesselsettings",
            constraint=models.CheckConstraint(
                condition=models.Q(solver_time_limit_seconds__lte=600),
                name="solver_time_limit_at_most_600",
            ),
        ),
    ]
