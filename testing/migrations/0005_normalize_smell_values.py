"""Normalise legacy free-text smell values (e.g. "Fresh") to the choice keys."""

from django.db import migrations

VALID = {'fresh', 'slightly_sour', 'strongly_sour', 'musty', 'rotten', 'other'}


def normalise_smell(apps, schema_editor):
    FeedSample = apps.get_model('testing', 'FeedSample')
    for sample in FeedSample.objects.exclude(smell__in=VALID).iterator():
        candidate = sample.smell.strip().lower().replace(' ', '_').replace('-', '_')
        sample.smell = candidate if candidate in VALID else 'other'
        sample.save(update_fields=['smell'])


class Migration(migrations.Migration):
    dependencies = [('testing', '0004_structured_findings_and_contact')]

    operations = [migrations.RunPython(normalise_smell, migrations.RunPython.noop)]
