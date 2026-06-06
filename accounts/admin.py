import json
import logging
from decimal import Decimal
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction, IntegrityError

logger = logging.getLogger('banking.admin')


class SafeAdminLogMixin:
    """
    Protège les actions admin contre les FK violations sur django_admin_log.
    Utilise des savepoints pour que le rollback du log n'annule pas le save du modèle.
    """

    def _safe_log(self, fn, *args, **kwargs):
        sid = db_transaction.savepoint()
        try:
            result = fn(*args, **kwargs)
            db_transaction.savepoint_commit(sid)
            return result
        except IntegrityError as exc:
            db_transaction.savepoint_rollback(sid)
            logger.error("django_admin_log FK failure ignorée (session désynchronisée) : %s", exc)

    def log_addition(self, request, obj, message):
        return self._safe_log(super().log_addition, request, obj, message)

    def log_change(self, request, obj, message):
        return self._safe_log(super().log_change, request, obj, message)

    def log_deletion(self, request, obj, object_repr):
        return self._safe_log(super().log_deletion, request, obj, object_repr)

    def log_deletions(self, request, queryset):
        return self._safe_log(super().log_deletions, request, queryset)

from .models import BankUser, BankAccount, Beneficiary, AuditLog, LoginAttempt
from .services import AccountService
from .constants import COUNTRY_BANKING_DATA


# ── Helpers ───────────────────────────────────────────────────────────────

def _get_credit_mutuel_bank():
    """Retourne la banque Crédit Mutuel active (première banque active configurée)."""
    from banks.models import Bank
    bank = Bank.objects.filter(is_active=True).first()
    if bank is None:
        raise ValidationError(
            "Aucune banque configurée. Veuillez d'abord créer la banque Crédit Mutuel dans l'admin."
        )
    return bank


# ── BankUser (masqué du menu — comptes créés via AccountService) ──────────

@admin.register(BankUser)
class BankUserAdmin(UserAdmin):
    list_display = ['account_id', 'email', 'is_active', 'is_staff', 'date_joined']
    search_fields = ['account_id', 'email']
    ordering = ['-date_joined']
    fieldsets = (
        (None, {'fields': ('account_id', 'password')}),
        ('Email', {'fields': ('email',)}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('account_id', 'email', 'password1', 'password2')}),
    )

    def get_model_perms(self, request):
        return {}

    def has_delete_permission(self, request, obj=None):
        # Interdire la suppression de tout superutilisateur via l'admin
        if obj is not None and obj.is_superuser:
            return False
        return super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        # Interdire la suppression en masse de superutilisateurs
        queryset.exclude(is_superuser=True).delete()


# ── BankAccount ───────────────────────────────────────────────────────────

@admin.register(BankAccount)
class BankAccountAdmin(SafeAdminLogMixin, admin.ModelAdmin):
    list_display = [
        'get_full_name', 'account_id_display', 'country',
        'currency', 'balance_display', 'status_badge',
        'manager_name', 'created_at',
    ]
    list_filter = ['status', 'country', 'currency']
    list_select_related = ['bank', 'user']
    search_fields = ['first_name', 'last_name', 'account_id', 'rib', 'email', 'phone']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        return super().get_queryset(request).filter(account_type=BankAccount.TYPE_COURANT)

    _ADD_FIELDSETS = (
        ('Gestionnaire', {
            'fields': ('manager_name',),
        }),
        ('Informations personnelles', {
            'fields': ('first_name', 'last_name', 'email', 'phone', 'country', 'address', 'birth_date'),
        }),
        ('Codes bancaires Crédit Mutuel', {
            'fields': ('banking_codes_preview',),
            'description': (
                'Codes générés automatiquement selon le pays sélectionné — '
                'agence Crédit Mutuel de la capitale du pays.'
            ),
        }),
        ('Compte', {
            'fields': ('balance', 'status'),
            'description': 'La devise est automatiquement déterminée par le pays sélectionné.',
        }),
        ('Blocage du compte', {
            'fields': ('block_reason', 'unblock_fee'),
            'classes': ('collapse',),
            'description': (
                '⚠️ Remplir uniquement si le statut est "Compte bloqué". '
                'Le motif de blocage est alors obligatoire.'
            ),
        }),
    )

    _CHANGE_FIELDSETS = (
        ('Banque & Gestionnaire', {
            'fields': ('bank', 'manager_name'),
        }),
        ('Identifiants générés automatiquement', {
            'fields': ('credentials_display', 'login_url_display', 'account_id', 'rib'),
            'classes': ('collapse',),
            'description': (
                'Ces informations ont été envoyées automatiquement par email au titulaire.'
            ),
        }),
        ('Informations personnelles', {
            'fields': ('first_name', 'last_name', 'email', 'phone', 'country', 'address', 'birth_date'),
        }),
        ('Compte', {
            'fields': ('currency', 'balance', 'status'),
        }),
        ('Blocage du compte', {
            'fields': ('block_reason', 'unblock_fee'),
            'description': '⚠️ Remplir uniquement si le statut est "Compte bloqué". Le motif est obligatoire.',
        }),
        ('Horodatage', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def get_fieldsets(self, request, obj=None):
        return self._ADD_FIELDSETS if obj is None else self._CHANGE_FIELDSETS

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ['banking_codes_preview']
        return [
            'bank', 'account_id', 'rib',
            'credentials_display', 'login_url_display',
            'created_at', 'updated_at',
        ]

    def get_form(self, request, obj=None, **kwargs):
        from django import forms
        from .constants import COUNTRY_LIST

        exclude = list(kwargs.get('exclude') or [])

        # Toujours exclure : callables readonly + champs non-éditables (auto_now)
        # Django 6.x lève FieldError si un champ non-éditable est dans le formulaire,
        # même s'il est listé dans readonly_fields.
        always_exclude = [
            'banking_codes_preview',  # callable JS, pas un champ modèle
            'credentials_display',    # callable readonly
            'login_url_display',      # callable readonly
            'created_at',             # auto_now_add → non éditable
            'updated_at',             # auto_now → non éditable
        ]
        for f in always_exclude:
            if f not in exclude:
                exclude.append(f)

        if obj is None:
            # À la création : ces champs sont générés automatiquement → exclure du formulaire
            for f in ('bank', 'account_id', 'rib', 'plain_password', 'user', 'is_primary', 'account_type'):
                if f not in exclude:
                    exclude.append(f)

        kwargs['exclude'] = exclude
        form = super().get_form(request, obj, **kwargs)
        if 'country' in form.base_fields:
            form.base_fields['country'] = forms.ChoiceField(
                choices=[('', '— Choisir un pays —')] + [(c, c) for c in COUNTRY_LIST],
                label='Pays',
            )
        return form

    # ── Display helpers ───────────────────────────────────────────────────

    def get_full_name(self, obj):
        return obj.get_full_name()
    get_full_name.short_description = 'Titulaire'
    get_full_name.admin_order_field = 'last_name'

    def account_id_display(self, obj):
        return format_html(
            '<span style="font-family:monospace;font-size:12px;">{}</span>'
            '<br><small style="color:#6b7280;">{}</small>',
            obj.account_id, obj.get_account_type_display()
        )
    account_id_display.short_description = 'Identifiant'
    account_id_display.admin_order_field = 'account_id'

    def balance_display(self, obj):
        color  = '#16a34a' if obj.balance >= 0 else '#dc2626'
        amount = f'{obj.balance:,.2f}'
        return format_html(
            '<span style="color:{};font-weight:700;font-family:monospace;">{} {}</span>',
            color, amount, obj.currency
        )
    balance_display.short_description = 'Solde'
    balance_display.admin_order_field = 'balance'

    def status_badge(self, obj):
        if obj.status == BankAccount.STATUS_ACTIVE:
            return mark_safe(
                '<span style="background:#dcfce7;color:#166534;padding:3px 10px;'
                'border-radius:12px;font-size:11px;font-weight:600;">● Actif</span>'
            )
        return mark_safe(
            '<span style="background:#fee2e2;color:#991b1b;padding:3px 10px;'
            'border-radius:12px;font-size:11px;font-weight:600;">🔒 Bloqué</span>'
        )
    status_badge.short_description = 'Statut'

    def banking_codes_preview(self, obj):
        """Affiche les codes Crédit Mutuel selon le pays — mis à jour dynamiquement par JS."""
        data_json = json.dumps(COUNTRY_BANKING_DATA, ensure_ascii=False)
        return mark_safe(f"""
        <div id="banking-codes-box"
             style="background:#f8fafc;border:1px solid #cbd5e1;border-radius:8px;
                    padding:16px;min-width:320px;font-family:sans-serif;">
            <p style="margin:0;font-size:12px;color:#94a3b8;">
                Sélectionnez un pays ci-dessus pour afficher les codes automatiques.
            </p>
        </div>
        <script>
        (function() {{
            var DATA = {data_json};

            function renderBox(country) {{
                var box = document.getElementById('banking-codes-box');
                if (!box) return;
                var d = DATA[country];
                if (!d) {{
                    box.innerHTML = '<p style="margin:0;font-size:12px;color:#94a3b8;">Sélectionnez un pays pour afficher les codes Crédit Mutuel.</p>';
                    return;
                }}
                box.style.borderColor = '#cc0000';
                box.innerHTML =
                    '<p style="margin:0 0 12px;font-size:13px;font-weight:700;color:#cc0000;text-transform:uppercase;letter-spacing:.04em;">' +
                    '🏦 Crédit Mutuel — ' + country + '</p>' +
                    '<table style="border-collapse:collapse;font-size:13px;width:100%;">' +
                    '<tr><td style="color:#64748b;padding:5px 24px 5px 0;white-space:nowrap;font-weight:600;">Code banque</td>' +
                    '<td><code style="background:#fef2f2;color:#cc0000;padding:3px 10px;border-radius:4px;font-size:13px;font-weight:700;">' + d.code_banque + '</code></td></tr>' +
                    '<tr><td style="color:#64748b;padding:5px 24px 5px 0;font-weight:600;">Code guichet</td>' +
                    '<td><code style="background:#fef2f2;color:#cc0000;padding:3px 10px;border-radius:4px;font-size:13px;font-weight:700;">' + d.code_guichet + '</code></td></tr>' +
                    '<tr><td style="color:#64748b;padding:5px 24px 5px 0;font-weight:600;">SWIFT / BIC</td>' +
                    '<td><code style="background:#fef2f2;color:#cc0000;padding:3px 10px;border-radius:4px;font-size:13px;font-weight:700;">' + d.swift + '</code></td></tr>' +
                    '</table>' +
                    '<p style="margin:10px 0 0;font-size:11px;color:#94a3b8;">✓ Clé RIB calculée automatiquement — agence capitale du pays.</p>';
            }}

            function attachSelect() {{
                /* Essaie plusieurs sélecteurs pour trouver le champ pays */
                var sel = document.getElementById('id_country')
                       || document.querySelector('select[name="country"]')
                       || document.querySelector('[name="country"]');
                if (sel) {{
                    sel.addEventListener('change', function() {{ renderBox(this.value); }});
                    renderBox(sel.value);
                    return true;
                }}
                return false;
            }}

            /* Retry toutes les 150ms pendant 3s au cas où l'admin charge ses JS après */
            var tries = 0;
            var timer = setInterval(function() {{
                if (attachSelect() || ++tries > 20) clearInterval(timer);
            }}, 150);

            /* Aussi tenter immédiatement et au chargement complet */
            attachSelect();
            window.addEventListener('load', function() {{ attachSelect(); }});
        }})();
        </script>
        """)
    banking_codes_preview.short_description = 'Codes bancaires Crédit Mutuel'

    def credentials_display(self, obj):
        if not obj.pk:
            return mark_safe('<em style="color:#6b7280;">Disponible après la création du compte.</em>')
        return format_html(
            '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;">'
            '<p style="margin:0 0 8px;font-size:13px;color:#374151;">'
            '<strong>Identifiant :</strong> '
            '<code style="background:#e2e8f0;padding:3px 8px;border-radius:4px;font-size:13px;">{}</code></p>'
            '<p style="margin:0;font-size:12px;color:#9ca3af;">'
            '✉️ Envoyé par email au titulaire avec le lien de création du mot de passe.</p>'
            '</div>',
            obj.account_id
        )
    credentials_display.short_description = 'Identifiant du compte'

    def login_url_display(self, obj):
        if not obj.pk:
            return '—'
        url = obj.get_login_url()
        return format_html(
            '<a href="{}" target="_blank" style="color:#2563eb;text-decoration:none;'
            'font-family:monospace;font-size:12px;">{}</a>',
            url, url
        )
    login_url_display.short_description = 'Lien de connexion'

    # ── Response overrides ────────────────────────────────────────────────

    def response_add(self, request, obj, post_url_continue=None):
        if getattr(request, '_save_error', False):
            from django.http import HttpResponseRedirect
            return HttpResponseRedirect(request.path)
        return super().response_add(request, obj, post_url_continue)

    # ── Save model ────────────────────────────────────────────────────────

    def save_model(self, request, obj, form, change):
        actor = request.user.get_username()

        if not change:
            # Récupérer la banque CM en tout premier et l'assigner à obj
            # (nécessaire pour que __str__ fonctionne même en cas d'erreur)
            try:
                bank = _get_credit_mutuel_bank()
            except ValidationError as e:
                messages.error(request, str(e.message))
                request._save_error = True
                return

            obj.bank = bank  # assigner immédiatement pour éviter bank=None

            # Vérifier qu'un compte courant n'existe pas déjà pour cet email
            try:
                from .models import BankUser
                existing_user = BankUser.objects.get(email=obj.email)
                if existing_user.bank_accounts.filter(
                    bank=bank, account_type=BankAccount.TYPE_COURANT
                ).exists():
                    messages.error(request, mark_safe(
                        f'⚠️ Un compte pour <strong>{obj.email}</strong> existe déjà dans '
                        f'<strong>{bank.name}</strong>. Consultez ou modifiez le compte existant.'
                    ))
                    request._save_error = True
                    return
            except BankUser.DoesNotExist:
                pass

            data = {
                'first_name':   obj.first_name,
                'last_name':    obj.last_name,
                'email':        obj.email,
                'phone':        obj.phone,
                'country':      obj.country,
                'address':      obj.address,
                'birth_date':   obj.birth_date,
                'currency':     obj.currency or '',
                'balance':      obj.balance,
                'status':       obj.status,
                'block_reason': obj.block_reason,
                'unblock_fee':  obj.unblock_fee,
                'manager_name': obj.manager_name,
                'account_type': BankAccount.TYPE_COURANT,
            }
            try:
                account, _ = AccountService.create_account(bank, data, actor=actor)

                obj.pk          = account.pk
                obj.account_id  = account.account_id
                obj.rib         = account.rib
                obj.user        = account.user
                obj.bank        = bank

                from .constants import COUNTRY_BANKING_DATA
                from django.conf import settings as _s
                banking  = COUNTRY_BANKING_DATA.get(account.country, {})
                swift    = banking.get('swift', bank.swift)

                # Construire l'URL depuis le domaine de la requête actuelle
                # (évite de dépendre de SITE_URL qui peut être en retard)
                base_url = (
                    f"{request.scheme}://{request.get_host()}"
                    if request.get_host() not in ('localhost', '127.0.0.1', 'testserver')
                    else _s.SITE_URL
                )
                login_url  = f"{base_url}/{bank.slug}/login/"
                setpwd_url = f"{base_url}/{bank.slug}/set-password/?id={account.user.account_id}"

                messages.success(request, mark_safe(
                    f'<div style="line-height:1.8;">'
                    f'<strong style="font-size:14px;">✅ Compte créé — {account.get_full_name()}</strong><br>'
                    f'<table style="margin-top:6px;border-collapse:collapse;">'
                    f'<tr><td style="padding:2px 16px 2px 0;"><strong>Identifiant :</strong></td>'
                    f'<td><code style="background:#e2e8f0;padding:2px 8px;border-radius:4px;">'
                    f'{account.user.account_id}</code></td></tr>'
                    f'<tr><td style="padding:2px 16px 2px 0;"><strong>RIB :</strong></td>'
                    f'<td><code style="background:#e2e8f0;padding:2px 8px;border-radius:4px;">'
                    f'{account.rib}</code></td></tr>'
                    f'<tr><td style="padding:2px 16px 2px 0;"><strong>SWIFT :</strong></td>'
                    f'<td><code style="background:#e2e8f0;padding:2px 8px;border-radius:4px;">'
                    f'{swift}</code></td></tr>'
                    f'<tr><td style="padding:2px 16px 2px 0;"><strong>Connexion :</strong></td>'
                    f'<td><a href="{login_url}" target="_blank" style="color:#2563eb;">'
                    f'{login_url}</a></td></tr>'
                    f'<tr><td style="padding:2px 16px 2px 0;"><strong>Lien 1ère connexion :</strong></td>'
                    f'<td><a href="{setpwd_url}" target="_blank" style="color:#2563eb;font-size:11px;">'
                    f'{setpwd_url}</a></td></tr>'
                    f'</table>'
                    f'<p style="margin:8px 0 0;font-size:12px;color:#059669;">'
                    f'✉️ Un email a été envoyé à <strong>{account.email}</strong> '
                    f'avec l\'identifiant et le lien pour créer le mot de passe.</p>'
                    f'</div>'
                ))

                def _send_creation_email(acc=account):
                    try:
                        from .utils import send_account_creation_email
                        send_account_creation_email(acc)
                    except Exception as e:
                        logger.warning("Email création compte non envoyé pour %s : %s", acc.account_id, e)
                db_transaction.on_commit(_send_creation_email)

                return

            except ValidationError as e:
                messages.error(request, f"Erreur de validation : {'; '.join(e.messages)}")
                request._save_error = True
                return
            except Exception as e:
                logger.exception("Erreur inattendue création compte pour %s", getattr(obj, 'email', '?'))
                messages.error(request, f"Erreur inattendue lors de la création : {e}")
                request._save_error = True
                return

        else:
            try:
                old = BankAccount.objects.get(pk=obj.pk)
                if old.status != obj.status:
                    AccountService.set_account_status(
                        old,
                        new_status=obj.status,
                        block_reason=obj.block_reason,
                        unblock_fee=obj.unblock_fee,
                        actor=actor,
                    )
                    if obj.status == BankAccount.STATUS_ACTIVE:
                        obj.block_reason = ''
            except ValidationError as e:
                messages.error(request, str(e.message))
                raise

            super().save_model(request, obj, form, change)


# ── Beneficiary ───────────────────────────────────────────────────────────

@admin.register(Beneficiary)
class BeneficiaryAdmin(admin.ModelAdmin):
    list_display = ['get_full_name', 'account', 'account_number', 'bank_name', 'email', 'created_at']
    search_fields = ['first_name', 'last_name', 'account_number', 'bank_name', 'account__account_id']
    list_filter = ['account__bank']
    list_select_related = ['account', 'account__bank']

    def get_full_name(self, obj):
        return obj.get_full_name()
    get_full_name.short_description = 'Bénéficiaire'


# ── AuditLog ──────────────────────────────────────────────────────────────

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'action_badge', 'actor', 'account', 'bank', 'description_short']
    list_filter = ['action', 'bank', 'created_at']
    search_fields = ['actor', 'description', 'account__account_id', 'account__first_name', 'account__last_name']
    list_select_related = ['bank', 'account']
    readonly_fields = ['bank', 'account', 'action', 'actor', 'description', 'extra_data', 'ip_address', 'created_at']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def action_badge(self, obj):
        color_map = {
            'account_created':    ('#dcfce7', '#166534'),
            'account_blocked':    ('#fee2e2', '#991b1b'),
            'account_unblocked':  ('#dbeafe', '#1e40af'),
            'transfer_created':   ('#fef9c3', '#92400e'),
            'transfer_validated': ('#dcfce7', '#166534'),
            'transfer_rejected':  ('#fee2e2', '#991b1b'),
            'balance_updated':    ('#e0e7ff', '#3730a3'),
            'login':              ('#f3f4f6', '#374151'),
            'password_changed':   ('#fdf4ff', '#7e22ce'),
        }
        bg, fg = color_map.get(obj.action, ('#f3f4f6', '#374151'))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;border-radius:10px;'
            'font-size:11px;white-space:nowrap;">{}</span>',
            bg, fg, obj.get_action_display()
        )
    action_badge.short_description = 'Action'

    def description_short(self, obj):
        return obj.description[:80] + ('…' if len(obj.description) > 80 else '')
    description_short.short_description = 'Description'


# ── LoginAttempt ──────────────────────────────────────────────────────────

@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'account_id', 'ip_address', 'bank_slug', 'success_badge']
    list_filter = ['success', 'bank_slug', 'created_at']
    search_fields = ['account_id', 'ip_address']
    readonly_fields = ['account_id', 'ip_address', 'bank_slug', 'success', 'created_at']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def success_badge(self, obj):
        if obj.success:
            return mark_safe(
                '<span style="background:#dcfce7;color:#166534;padding:2px 8px;'
                'border-radius:10px;font-size:11px;">✓ Succès</span>'
            )
        return mark_safe(
            '<span style="background:#fee2e2;color:#991b1b;padding:2px 8px;'
            'border-radius:10px;font-size:11px;">✗ Échec</span>'
        )
    success_badge.short_description = 'Résultat'
