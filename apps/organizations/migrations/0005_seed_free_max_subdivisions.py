from django.db import migrations

# Per-location subdivision caps by tier. null = unlimited.
SUBDIVISION_LIMITS = {
    "free": 5,
    "pro": None,
    "enterprise": None,
}


def seed_max_subdivisions(apps, schema_editor):
    Plan = apps.get_model("organizations", "Plan")
    for tier, limit in SUBDIVISION_LIMITS.items():
        Plan.objects.filter(tier=tier).update(max_subdivisions=limit)


def unseed_max_subdivisions(apps, schema_editor):
    Plan = apps.get_model("organizations", "Plan")
    Plan.objects.update(max_subdivisions=None)


class Migration(migrations.Migration):
    dependencies = [("organizations", "0004_add_max_subdivisions")]
    operations = [migrations.RunPython(seed_max_subdivisions, unseed_max_subdivisions)]
