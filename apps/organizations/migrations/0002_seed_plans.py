from django.db import migrations

PLANS = [
    {
        "tier": "free",
        "name": "Free",
        "max_locations": 2,
        "max_items": 25,
        "max_members": 3,
        "monthly_price_cents": 0,
    },
    {
        "tier": "pro",
        "name": "Pro",
        "max_locations": 25,
        "max_items": 1000,
        "max_members": 25,
        "monthly_price_cents": 2900,
    },
    {
        "tier": "enterprise",
        "name": "Enterprise",
        "max_locations": None,
        "max_items": None,
        "max_members": None,
        "monthly_price_cents": 0,
    },
]


def seed_plans(apps, schema_editor):
    Plan = apps.get_model("organizations", "Plan")
    for data in PLANS:
        Plan.objects.update_or_create(tier=data["tier"], defaults=data)


def unseed_plans(apps, schema_editor):
    Plan = apps.get_model("organizations", "Plan")
    Plan.objects.filter(tier__in=[p["tier"] for p in PLANS]).delete()


class Migration(migrations.Migration):
    dependencies = [("organizations", "0001_initial")]
    operations = [migrations.RunPython(seed_plans, unseed_plans)]
