from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Bank


@admin.register(Bank)
class BankAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'country', 'swift', 'color_preview', 'is_active']
    list_filter = ['is_active', 'country']
    search_fields = ['name', 'slug', 'swift']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['color_preview_full', 'login_url_preview', 'seo_preview']

    fieldsets = (
        ('Identité', {
            'fields': ('name', 'slug', 'logo', 'tagline', 'is_active')
        }),
        ('Coordonnées', {
            'fields': ('address',)
        }),
        ('Informations bancaires', {
            'fields': ('swift', 'bank_code', 'country')
        }),
        ('Charte graphique', {
            'fields': (
                'color_primary', 'color_secondary', 'color_accent',
                'color_text_on_primary', 'color_background',
                'color_card', 'color_card_text',
                'color_preview_full',
            )
        }),
        ('SEO & Partage de lien', {
            'fields': (
                'meta_description',
                'favicon_url', 'favicon',
                'og_image_url', 'og_image',
                'seo_preview',
            ),
            'description': (
                '<strong>URLs externes</strong> (prioritaires) : collez directement une URL de favicon ou d\'image OG.<br>'
                '<strong>Fichiers uploadés</strong> : utilisés si les URLs externes sont vides.<br>'
                'Format OG recommandé : 1200×630 px — affiché lors du partage sur WhatsApp, iMessage, réseaux sociaux.'
            ),
        }),
        ('URL de connexion', {
            'fields': ('login_url_preview',)
        }),
    )

    def color_preview(self, obj):
        return format_html(
            '<span style="display:inline-block;width:24px;height:24px;background:{};border-radius:4px;border:1px solid #ccc;vertical-align:middle;margin-right:4px;"></span>'
            '<span style="display:inline-block;width:24px;height:24px;background:{};border-radius:4px;border:1px solid #ccc;vertical-align:middle;"></span>',
            obj.color_primary, obj.color_secondary
        )
    color_preview.short_description = 'Couleurs'

    def color_preview_full(self, obj):
        swatches = [
            (obj.color_primary, 'Primaire'),
            (obj.color_secondary, 'Secondaire'),
            (obj.color_accent, 'Accent'),
            (obj.color_background, 'Arrière-plan'),
            (obj.color_card, 'Carte'),
        ]
        parts = [mark_safe('<div style="display:flex;gap:12px;flex-wrap:wrap;">')]
        for color, label in swatches:
            parts.append(format_html(
                '<div style="text-align:center;">'
                '<div style="width:60px;height:40px;background:{};border-radius:6px;border:1px solid #ccc;"></div>'
                '<small>{}<br>{}</small>'
                '</div>',
                color, label, color
            ))
        parts.append(mark_safe('</div>'))
        return mark_safe(''.join(str(p) for p in parts))
    color_preview_full.short_description = 'Aperçu des couleurs'

    def login_url_preview(self, obj):
        url = obj.get_login_url()
        return format_html('<a href="{}" target="_blank">{}</a>', url, url)
    login_url_preview.short_description = 'URL de connexion'

    def seo_preview(self, obj):
        favicon_url = obj.effective_favicon_url
        og_url      = obj.effective_og_image_url
        desc        = obj.effective_meta_description

        favicon_html = (
            format_html(
                '<img src="{}" style="width:32px;height:32px;object-fit:contain;'
                'border-radius:4px;vertical-align:middle;margin-right:8px;">'
                '<a href="{}" target="_blank" style="font-size:11px;color:#2563eb;">{}</a>',
                favicon_url, favicon_url, favicon_url[:60] + ('…' if len(favicon_url) > 60 else '')
            ) if favicon_url else mark_safe('<em style="color:#9ca3af;">Aucun favicon défini</em>')
        )

        og_html = (
            format_html(
                '<img src="{}" style="max-width:240px;max-height:120px;border-radius:6px;'
                'object-fit:cover;display:block;margin-bottom:6px;">'
                '<a href="{}" target="_blank" style="font-size:11px;color:#2563eb;">{}</a>',
                og_url, og_url, og_url[:60] + ('…' if len(og_url) > 60 else '')
            ) if og_url else mark_safe('<em style="color:#9ca3af;">Aucune image OG définie</em>')
        )

        return mark_safe(f'''
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;max-width:540px;">
            <p style="font-size:11px;font-weight:700;color:#374151;text-transform:uppercase;
                      letter-spacing:.06em;margin:0 0 10px;">Favicon actif</p>
            <div style="margin-bottom:16px;">{favicon_html}</div>
            <p style="font-size:11px;font-weight:700;color:#374151;text-transform:uppercase;
                      letter-spacing:.06em;margin:0 0 10px;">Image de partage (OG)</p>
            <div style="margin-bottom:16px;">{og_html}</div>
            <p style="font-size:11px;font-weight:700;color:#374151;text-transform:uppercase;
                      letter-spacing:.06em;margin:0 0 6px;">Description SEO</p>
            <p style="font-size:12px;color:#374151;margin:0;">{desc}</p>
        </div>
        ''')
    seo_preview.short_description = 'Aperçu SEO & partage'
