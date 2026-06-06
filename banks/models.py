from django.db import models


class Bank(models.Model):
    name = models.CharField(max_length=200, verbose_name="Nom de la banque")
    slug = models.SlugField(unique=True, verbose_name="Slug (URL de connexion)")
    logo = models.ImageField(upload_to='banks/logos/', verbose_name="Logo")
    tagline = models.CharField(max_length=300, blank=True, verbose_name="Slogan")

    address = models.TextField(verbose_name="Adresse du siège")
    phone = models.CharField(max_length=30, verbose_name="Téléphone")
    email = models.EmailField(verbose_name="Email officiel")
    website = models.URLField(blank=True, verbose_name="Site web")
    swift = models.CharField(max_length=11, verbose_name="Code SWIFT/BIC")
    bank_code = models.CharField(max_length=10, verbose_name="Code banque")
    country = models.CharField(max_length=100, default='France', verbose_name="Pays siège")

    # Charte graphique
    color_primary = models.CharField(max_length=7, default='#1a3a5c', verbose_name="Couleur primaire")
    color_secondary = models.CharField(max_length=7, default='#2ecc71', verbose_name="Couleur secondaire")
    color_accent = models.CharField(max_length=7, default='#f39c12', verbose_name="Couleur accent")
    color_text_on_primary = models.CharField(max_length=7, default='#ffffff', verbose_name="Texte sur couleur primaire")
    color_background = models.CharField(max_length=7, default='#f8f9fa', verbose_name="Couleur arrière-plan")
    color_card = models.CharField(max_length=7, default='#1a3a5c', verbose_name="Couleur carte bancaire")
    color_card_text = models.CharField(max_length=7, default='#ffffff', verbose_name="Texte sur carte bancaire")

    # SEO & partage de lien — fichiers uploadés
    favicon = models.FileField(upload_to='banks/favicons/', blank=True, null=True, verbose_name="Favicon (fichier uploadé)")
    meta_description = models.CharField(max_length=160, blank=True, verbose_name="Description SEO (160 car. max)")
    og_image = models.ImageField(upload_to='banks/og/', blank=True, null=True, verbose_name="Image Open Graph (fichier uploadé)")

    # URLs externes — prioritaires sur les fichiers uploadés
    logo_url = models.URLField(
        blank=True,
        verbose_name="URL logo externe",
        help_text="URL directe vers le logo affiché sur le site (prioritaire sur le fichier uploadé).",
    )
    favicon_url = models.URLField(
        blank=True,
        verbose_name="URL favicon externe",
        help_text="URL directe vers le favicon (onglet navigateur uniquement).",
    )
    og_image_url = models.URLField(
        blank=True,
        verbose_name="URL image Open Graph externe",
        help_text="URL directe vers l'image de partage (prioritaire sur le fichier uploadé).",
    )

    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Banque active")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Banque"
        verbose_name_plural = "Banques"
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_login_url(self):
        return f"/{self.slug}/login/"

    @property
    def effective_logo_url(self) -> str:
        """URL logo pour le site : logo_url externe > logo uploadé > favicon uploadée."""
        if self.logo_url:
            return self.logo_url
        if self.logo:
            try:
                return self.logo.url
            except Exception:
                pass
        if self.favicon:
            try:
                return self.favicon.url
            except Exception:
                pass
        return ''

    @property
    def effective_favicon_url(self) -> str:
        """URL favicon finale : URL externe si définie, sinon fichier uploadé."""
        if self.favicon_url:
            return self.favicon_url
        if self.favicon:
            try:
                return self.favicon.url
            except Exception:
                pass
        return ''

    @property
    def effective_og_image_url(self) -> str:
        """URL image OG finale : URL externe si définie, sinon fichier uploadé."""
        if self.og_image_url:
            return self.og_image_url
        if self.og_image:
            try:
                return self.og_image.url
            except Exception:
                pass
        return ''

    @property
    def effective_meta_description(self) -> str:
        """Description SEO : champ DB si rempli, sinon description CM par défaut."""
        return self.meta_description or (
            f"{self.name} — Banque mutualiste. Gérez votre compte bancaire en ligne "
            "en toute sécurité, depuis n'importe quel appareil, 24h/24 et 7j/7."
        )
