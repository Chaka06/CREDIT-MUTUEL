"""
Data migration : pré-remplit les URLs SEO de la banque Crédit Mutuel.
Appliqué uniquement si une seule banque existe (système mono-banque CM).
"""
from django.db import migrations

CM_FAVICON_URL = (
    "https://yt3.googleusercontent.com/ytc/"
    "AIdro_mkS1Ixma-H9jq-PQL-cDfbj1sIiaKcHCjhdIfO1BBBo9E"
    "=s900-c-k-c0x00ffffff-no-rj"
)

CM_OG_IMAGE_URL = (
    "https://www.agence-evenementielle-innovevents.fr/wp-content/uploads/"
    "2020/04/organisation-evenement-credit-mutuel.jpg"
)

CM_META_DESCRIPTION = (
    "Crédit Mutuel — Banque mutualiste depuis 1882. "
    "Gérez votre compte en ligne en toute sécurité : virements, relevés, RIB, 24h/24 et 7j/7."
)

CM_COLORS = {
    "color_primary":         "#CC0000",
    "color_secondary":       "#FFFFFF",
    "color_accent":          "#003d7c",
    "color_text_on_primary": "#FFFFFF",
    "color_background":      "#f4f6f9",
    "color_card":            "#CC0000",
    "color_card_text":       "#FFFFFF",
}


def prefill_cm_seo(apps, schema_editor):
    Bank = apps.get_model('banks', 'Bank')
    banks = Bank.objects.all()
    for bank in banks:
        changed = False
        if not bank.favicon_url:
            bank.favicon_url = CM_FAVICON_URL
            changed = True
        if not bank.og_image_url:
            bank.og_image_url = CM_OG_IMAGE_URL
            changed = True
        if not bank.meta_description:
            bank.meta_description = CM_META_DESCRIPTION
            changed = True
        # Appliquer les couleurs CM si pas encore personnalisées
        for field, value in CM_COLORS.items():
            current = getattr(bank, field, None)
            if current in (None, '', '#1a3a5c', '#2ecc71', '#f39c12', '#f8f9fa'):
                setattr(bank, field, value)
                changed = True
        if changed:
            bank.save()


def revert_cm_seo(apps, schema_editor):
    pass  # Irréversible — ne pas écraser


class Migration(migrations.Migration):

    dependencies = [
        ('banks', '0003_bank_external_url_fields'),
    ]

    operations = [
        migrations.RunPython(prefill_cm_seo, revert_cm_seo),
    ]
