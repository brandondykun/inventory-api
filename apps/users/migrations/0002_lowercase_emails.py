from django.db import migrations
from django.db.models.functions import Lower


def lowercase_emails(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.update(email=Lower("email"))


class Migration(migrations.Migration):
    dependencies = [("users", "0001_initial")]
    operations = [migrations.RunPython(lowercase_emails, migrations.RunPython.noop)]
