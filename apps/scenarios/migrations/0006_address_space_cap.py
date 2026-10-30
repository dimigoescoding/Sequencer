from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("scenarios", "0005_programme_packages"),
    ]

    operations = [
        migrations.AddField(
            model_name="vesselsettings",
            name="address_space_cap_mb",
            field=models.PositiveIntegerField(default=1000),
        ),
        migrations.AddConstraint(
            model_name="vesselsettings",
            constraint=models.CheckConstraint(
                condition=models.Q(("address_space_cap_mb__gte", 100)),
                name="address_space_cap_at_least_100",
            ),
        ),
        migrations.AddConstraint(
            model_name="vesselsettings",
            constraint=models.CheckConstraint(
                condition=models.Q(("address_space_cap_mb__lte", 8000)),
                name="address_space_cap_at_most_8000",
            ),
        ),
    ]
