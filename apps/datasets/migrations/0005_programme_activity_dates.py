from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("datasets", "0004_programme_packages"),
    ]

    operations = [
        migrations.AddField(
            model_name="programmeslot",
            name="armour_p50_end",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="programmeslot",
            name="armour_p50_start",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="programmeslot",
            name="burial_p50_end",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="programmeslot",
            name="burial_p50_start",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="programmeslot",
            name="commissioning_p50_end",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="programmeslot",
            name="commissioning_p50_start",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="programmeslot",
            name="filter_p50_end",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="programmeslot",
            name="filter_p50_start",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="programmeslot",
            name="sst_p50_end",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="programmeslot",
            name="sst_p50_start",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
