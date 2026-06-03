from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('banks', '0002_add_seo_fields_to_bank'),
    ]

    operations = [
        migrations.AddField(
            model_name='bank',
            name='favicon_url',
            field=models.URLField(
                blank=True,
                verbose_name='URL favicon externe',
                help_text='URL directe vers le favicon (prioritaire sur le fichier uploadé).',
            ),
        ),
        migrations.AddField(
            model_name='bank',
            name='og_image_url',
            field=models.URLField(
                blank=True,
                verbose_name='URL image Open Graph externe',
                help_text="URL directe vers l'image de partage (prioritaire sur le fichier uploadé).",
            ),
        ),
    ]
