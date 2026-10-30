from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("optimisation", "0003_render_plan_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="optimisationrun",
            name="peak_address_bytes",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="optimisationrun",
            name="peak_rss_bytes",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
    ]
