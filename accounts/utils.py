"""
Utilitaires : génération de PDFs et envoi d'emails via Brevo (SMTP).
Toute la logique de génération d'identifiants est dans services.py.
"""
import io
import os
import math
import logging
from datetime import datetime
from django.conf import settings
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, KeepTogether,
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.lib.utils import ImageReader
import requests as _requests
from PIL import Image as _PILImage

logger = logging.getLogger('banking.utils')


# ── Brevo SMTP ────────────────────────────────────────────────────────────

def _send_email(from_name: str, to_email: str, subject: str, html_body: str) -> bool:
    if not to_email or not to_email.strip():
        logger.warning("_send_email: destinataire vide — email non envoyé (subject=%s)", subject)
        return False
    from django.core.mail import EmailMessage
    try:
        msg = EmailMessage(
            subject=subject,
            body=html_body,
            from_email=f"{from_name} <{settings.DEFAULT_FROM_EMAIL}>",
            to=[to_email],
        )
        msg.content_subtype = 'html'
        msg.send()
        logger.info("Email envoyé à %s | subject=%s", to_email, subject)
        return True
    except Exception as exc:
        logger.error("Échec envoi email à %s | subject=%s | erreur: %s", to_email, subject, exc, exc_info=True)
        return False


# ── Helpers style PayPal ──────────────────────────────────────────────────

def _email_header(bank) -> str:
    logo_html = ''
    if bank.logo:
        try:
            raw = bank.logo.url
            logo_url = raw if raw.startswith('http') else f"{settings.SITE_URL}{raw}"
            logo_html = f'<img src="{logo_url}" alt="{bank.name}" style="max-height:52px;max-width:150px;display:block;">'
        except Exception:
            pass

    if logo_html:
        content_cells = f'<td style="vertical-align:middle;">{logo_html}</td>'
    else:
        name_part = f'<span style="color:{bank.color_primary};font-size:17px;font-weight:700;font-family:Arial,Helvetica,sans-serif;">{bank.name}</span>'
        tagline_part = f'<br><span style="color:#888888;font-size:11px;font-family:Arial,Helvetica,sans-serif;">{bank.tagline}</span>' if bank.tagline else ''
        content_cells = f'<td style="vertical-align:middle;">{name_part}{tagline_part}</td>'

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-bottom:3px solid {bank.color_primary};">
      <tr>
        <td style="background:#ffffff;padding:18px 24px;">
          <table cellpadding="0" cellspacing="0" border="0">
            <tr>
              {content_cells}
            </tr>
          </table>
        </td>
      </tr>
    </table>"""


def _email_footer(bank) -> str:
    parts = [f'<strong style="color:#555555;">{bank.name}</strong>']
    if bank.address:
        parts.append(f'<span style="color:#888888;">{bank.address}</span>')
    if bank.phone:
        parts.append(f'<span style="color:#888888;">Tél&nbsp;: {bank.phone}</span>')
    if bank.email:
        parts.append(f'<a href="mailto:{bank.email}" style="color:#888888;text-decoration:none;">{bank.email}</a>')

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:32px;border-top:1px solid #dddddd;">
      <tr>
        <td style="padding:20px 24px;text-align:center;">
          <p style="margin:0 0 6px;font-size:11px;font-family:Arial,Helvetica,sans-serif;color:#aaaaaa;line-height:1.7;">
            {' &nbsp;·&nbsp; '.join(parts)}
          </p>
          <p style="margin:0;font-size:11px;font-family:Arial,Helvetica,sans-serif;color:#aaaaaa;line-height:1.7;">
            Ce message est confidentiel et destiné uniquement à son destinataire.
          </p>
        </td>
      </tr>
    </table>"""


def _email_wrap(bank, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#f5f5f5;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f5f5f5;">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;background:#ffffff;border:1px solid #dddddd;">
          <tr><td>{_email_header(bank)}</td></tr>
          <tr>
            <td style="padding:32px 24px;font-family:Arial,Helvetica,sans-serif;color:#333333;">
              {body}
              {_email_footer(bank)}
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _info_table(rows: list) -> str:
    html = '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0;border-top:1px solid #dddddd;">'
    for label, value in rows:
        html += f"""
        <tr>
          <td style="padding:12px 0;border-bottom:1px solid #dddddd;font-size:13px;color:#888888;font-family:Arial,Helvetica,sans-serif;width:45%;vertical-align:top;">{label}</td>
          <td style="padding:12px 0;border-bottom:1px solid #dddddd;font-size:13px;color:#333333;font-family:Arial,Helvetica,sans-serif;font-weight:700;text-align:right;vertical-align:top;">{value}</td>
        </tr>"""
    html += '</table>'
    return html


def _btn(label: str, url: str, color: str, text_color: str = '#ffffff') -> str:
    return f"""
    <table cellpadding="0" cellspacing="0" border="0" style="margin:28px 0;">
      <tr>
        <td style="background:{color};padding:14px 32px;">
          <a href="{url}" style="color:{text_color};font-size:14px;font-weight:700;font-family:Arial,Helvetica,sans-serif;text-decoration:none;display:block;">{label}</a>
        </td>
      </tr>
    </table>"""


def _alert(text: str, border_color: str, bg_color: str, text_color: str) -> str:
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0;">
      <tr>
        <td style="border-left:4px solid {border_color};background:{bg_color};padding:14px 18px;">
          <p style="margin:0;font-size:13px;font-family:Arial,Helvetica,sans-serif;color:{text_color};line-height:1.6;">{text}</p>
        </td>
      </tr>
    </table>"""


# ── Email : ouverture de compte ───────────────────────────────────────────

def send_account_creation_email(bank_account):
    bank      = bank_account.bank
    login_url = bank_account.get_login_url()

    set_pwd_url = f"{settings.SITE_URL}/{bank.slug}/set-password/?id={bank_account.account_id}"

    if bank_account.is_blocked:
        fee = (
            f"{bank_account.unblock_fee:,.2f} {bank_account.currency}"
            if bank_account.unblock_fee else "Aucuns frais"
        )
        status_html = _alert(
            f'<strong>Compte temporairement bloqué</strong><br>'
            f'Motif&nbsp;: {bank_account.block_reason}<br>'
            f'Frais de déblocage&nbsp;: {fee}',
            '#cc0000', '#fff8f8', '#cc0000'
        )
        status_html += (
            '<p style="font-size:14px;color:#555555;line-height:1.7;margin:8px 0 0;">'
            'Votre gestionnaire vous contactera pour la procédure de déblocage.</p>'
        )
        action_btn = ''
    else:
        status_html = _alert(
            'Votre compte est <strong>actif et opérationnel</strong>. '
            'Créez votre mot de passe pour accéder à votre espace bancaire.',
            '#2ea44f', '#f6fff9', '#1a7a38'
        )
        action_btn = _btn(
            'Créer mon mot de passe à 6 chiffres',
            set_pwd_url,
            bank.color_primary,
            bank.color_text_on_primary,
        )

    body = f"""
    <p style="font-size:16px;font-weight:700;color:#333333;margin:0 0 6px;font-family:Arial,Helvetica,sans-serif;">Bonjour {bank_account.first_name},</p>
    <p style="font-size:14px;color:#555555;line-height:1.7;margin:0 0 20px;">
      Votre compte bancaire vient d'être ouvert chez <strong>{bank.name}</strong>.
      Voici vos informations d'accès.
    </p>

    <table width="100%" cellpadding="0" cellspacing="0" border="0"
           style="background:#f0f4ff;border:2px solid {bank.color_primary};
                  border-radius:10px;margin:0 0 24px;text-align:center;">
      <tr>
        <td style="padding:18px 24px;">
          <p style="margin:0 0 4px;font-size:11px;font-weight:700;color:#888888;
                    text-transform:uppercase;letter-spacing:.8px;font-family:Arial,Helvetica,sans-serif;">
            Votre identifiant de connexion
          </p>
          <p style="margin:0;font-size:32px;font-weight:800;font-family:'Courier New',monospace;
                    color:{bank.color_primary};letter-spacing:6px;">
            {bank_account.account_id}
          </p>
          <p style="margin:6px 0 0;font-size:11px;color:#aaaaaa;font-family:Arial,Helvetica,sans-serif;">
            Conservez cet identifiant précieusement — il vous sera demandé à chaque connexion.
          </p>
        </td>
      </tr>
    </table>

    {status_html}

    <p style="font-size:12px;font-weight:700;color:#888888;letter-spacing:.8px;text-transform:uppercase;
              margin:28px 0 0;font-family:Arial,Helvetica,sans-serif;">Détails du compte</p>
    {_info_table([
        ('Titulaire', bank_account.get_full_name()),
        ('Banque', bank.name),
        ('Devise', bank_account.currency),
        ('Gestionnaire', bank_account.manager_name),
    ])}

    {action_btn}

    {_alert(
        'Ne communiquez jamais votre identifiant ou votre mot de passe à qui que ce soit, '
        'y compris à votre conseiller bancaire.',
        '#cc0000', '#fff8f8', '#991b1b'
    )}
    """

    _send_email(
        from_name=bank.name,
        to_email=bank_account.email,
        subject=f"{bank.name} — Ouverture de votre compte — Créez votre mot de passe",
        html_body=_email_wrap(bank, body),
    )


# ── Email : virement initié (bénéficiaire) ────────────────────────────────

def send_transfer_initiated_email_to_beneficiary(transaction):
    beneficiary_email = transaction.get_beneficiary_display_email()
    if not beneficiary_email:
        return

    bank = transaction.account.bank

    body = f"""
    <p style="font-size:16px;font-weight:700;color:#333333;margin:0 0 6px;font-family:Arial,Helvetica,sans-serif;">Bonjour,</p>
    <p style="font-size:14px;color:#555555;line-height:1.7;margin:0 0 4px;">
      Un virement a été initié en votre faveur depuis <strong>{bank.name}</strong>.
    </p>
    <p style="font-size:28px;font-weight:700;color:#333333;font-family:Arial,Helvetica,sans-serif;margin:20px 0;">
      {transaction.amount:,.2f} <span style="font-size:16px;color:#888888;">{transaction.currency}</span>
    </p>
    {_info_table([
        ('Référence', transaction.reference),
        ("Donneur d'ordre", transaction.account.get_full_name()),
        ('Banque émettrice', bank.name),
        ('Motif', transaction.description or '—'),
    ])}
    {_alert(
        'Ce virement est en cours de validation. Vous recevrez la confirmation définitive sous <strong>48 heures ouvrées</strong>.',
        '#f0a500', '#fffdf0', '#7a5c00'
    )}
    """

    _send_email(
        from_name=bank.name,
        to_email=beneficiary_email,
        subject=f"Virement entrant en attente — Réf. {transaction.reference}",
        html_body=_email_wrap(bank, body),
    )


# ── Email : virement validé ───────────────────────────────────────────────

def send_transfer_validated_email(transaction):
    bank = transaction.account.bank
    validated_at = transaction.validated_at.strftime('%d/%m/%Y à %H:%M') if transaction.validated_at else '—'
    iban_bene = transaction.beneficiary.account_number if transaction.beneficiary else transaction.beneficiary_iban or '—'

    body_sender = f"""
    <p style="font-size:16px;font-weight:700;color:#333333;margin:0 0 6px;font-family:Arial,Helvetica,sans-serif;">Bonjour {transaction.account.first_name},</p>
    <p style="font-size:14px;color:#555555;line-height:1.7;margin:0 0 4px;">
      Votre virement a été <strong>validé avec succès</strong>.
    </p>
    <p style="font-size:28px;font-weight:700;color:#333333;font-family:Arial,Helvetica,sans-serif;margin:20px 0;">
      -{transaction.amount:,.2f} <span style="font-size:16px;color:#888888;">{transaction.currency}</span>
    </p>
    {_info_table([
        ('Référence', transaction.reference),
        ('Bénéficiaire', transaction.get_beneficiary_display_name()),
        ('IBAN bénéficiaire', iban_bene),
        ('Motif', transaction.description or '—'),
        ('Validé le', validated_at),
    ])}
    """

    _send_email(
        from_name=bank.name,
        to_email=transaction.account.email,
        subject=f"Virement validé — Réf. {transaction.reference}",
        html_body=_email_wrap(bank, body_sender),
    )

    beneficiary_email = transaction.get_beneficiary_display_email()
    if beneficiary_email:
        body_bene = f"""
        <p style="font-size:16px;font-weight:700;color:#333333;margin:0 0 6px;font-family:Arial,Helvetica,sans-serif;">Bonjour,</p>
        <p style="font-size:14px;color:#555555;line-height:1.7;margin:0 0 4px;">
          Un virement a été <strong>validé</strong> en votre faveur.
        </p>
        <p style="font-size:28px;font-weight:700;color:#2ea44f;font-family:Arial,Helvetica,sans-serif;margin:20px 0;">
          +{transaction.amount:,.2f} <span style="font-size:16px;color:#888888;">{transaction.currency}</span>
        </p>
        {_info_table([
            ('Référence', transaction.reference),
            ('Émetteur', transaction.account.get_full_name()),
            ('Banque émettrice', bank.name),
            ('Validé le', validated_at),
        ])}
        """

        _send_email(
            from_name=bank.name,
            to_email=beneficiary_email,
            subject=f"Virement reçu — Réf. {transaction.reference}",
            html_body=_email_wrap(bank, body_bene),
        )


# ── Email : virement rejeté ───────────────────────────────────────────────

def send_transfer_rejected_email(transaction):
    bank = transaction.account.bank
    fee_text = f"{transaction.rejection_fee:,.2f} {transaction.currency}" if transaction.rejection_fee else "Aucuns frais"

    body_sender = f"""
    <p style="font-size:16px;font-weight:700;color:#333333;margin:0 0 6px;font-family:Arial,Helvetica,sans-serif;">Bonjour {transaction.account.first_name},</p>
    <p style="font-size:14px;color:#555555;line-height:1.7;margin:0 0 4px;">
      Votre virement a été <strong>rejeté</strong>. Le montant a été recrédité sur votre compte.
    </p>
    <p style="font-size:28px;font-weight:700;color:#cc0000;font-family:Arial,Helvetica,sans-serif;margin:20px 0;">
      {transaction.amount:,.2f} <span style="font-size:16px;color:#888888;">{transaction.currency}</span>
    </p>
    {_info_table([
        ('Référence', transaction.reference),
        ('Bénéficiaire', transaction.get_beneficiary_display_name()),
        ('Motif du rejet', transaction.rejection_reason),
        ('Frais de redirection', fee_text),
    ])}
    {_alert(
        f'Rendez-vous en agence muni de votre pièce d\'identité pour relancer ce virement. '
        f'Les frais de redirection ({fee_text}) sont réglés sur place.',
        '#f0a500', '#fffdf0', '#7a5c00'
    )}
    """

    _send_email(
        from_name=bank.name,
        to_email=transaction.account.email,
        subject=f"Virement rejeté — Réf. {transaction.reference}",
        html_body=_email_wrap(bank, body_sender),
    )

    beneficiary_email = transaction.get_beneficiary_display_email()
    if beneficiary_email:
        body_bene = f"""
        <p style="font-size:16px;font-weight:700;color:#333333;margin:0 0 6px;font-family:Arial,Helvetica,sans-serif;">Bonjour,</p>
        <p style="font-size:14px;color:#555555;line-height:1.7;margin:0 0 24px;">
          Le virement initié en votre faveur (réf. <strong>{transaction.reference}</strong>) a été annulé.
        </p>
        {_info_table([
            ('Référence', transaction.reference),
            ('Montant concerné', f"{transaction.amount:,.2f} {transaction.currency}"),
            ('Motif', transaction.rejection_reason),
        ])}
        <p style="font-size:13px;color:#888888;line-height:1.7;margin:0;">Pour toute question, contactez directement l'émetteur du virement.</p>
        """

        _send_email(
            from_name=bank.name,
            to_email=beneficiary_email,
            subject=f"Virement annulé — Réf. {transaction.reference}",
            html_body=_email_wrap(bank, body_bene),
        )


# ── Email : blocage de compte ─────────────────────────────────────────────

def send_account_blocked_email(bank_account):
    bank = bank_account.bank
    fee_text = f"{bank_account.unblock_fee:,.2f} {bank_account.currency}" if bank_account.unblock_fee else "Aucuns frais"

    body = f"""
    <p style="font-size:16px;font-weight:700;color:#333333;margin:0 0 6px;font-family:Arial,Helvetica,sans-serif;">Bonjour {bank_account.first_name},</p>
    <p style="font-size:14px;color:#555555;line-height:1.7;margin:0 0 24px;">
      Votre compte auprès de <strong>{bank.name}</strong> a été <strong>temporairement bloqué</strong>.
    </p>
    {_info_table([
        ('Identifiant du compte', bank_account.account_id),
        ('Motif du blocage', bank_account.block_reason),
        ('Frais de déblocage', fee_text),
        ('Gestionnaire', bank_account.manager_name),
    ])}
    {_alert(
        f'Contactez votre gestionnaire <strong>{bank_account.manager_name}</strong> pour obtenir la procédure de déblocage. '
        f'Si vous pensez qu\'il s\'agit d\'une erreur, contactez-nous immédiatement.',
        '#cc0000', '#fff8f8', '#cc0000'
    )}
    """

    _send_email(
        from_name=bank.name,
        to_email=bank_account.email,
        subject=f"{bank.name} — Votre compte a été bloqué",
        html_body=_email_wrap(bank, body),
    )


# ── Email : déblocage de compte ───────────────────────────────────────────

def send_account_unblocked_email(bank_account):
    bank = bank_account.bank

    body = f"""
    <p style="font-size:16px;font-weight:700;color:#333333;margin:0 0 6px;font-family:Arial,Helvetica,sans-serif;">Bonjour {bank_account.first_name},</p>
    <p style="font-size:14px;color:#555555;line-height:1.7;margin:0 0 24px;">
      Votre compte auprès de <strong>{bank.name}</strong> est à nouveau <strong>actif et pleinement opérationnel</strong>.
    </p>
    {_info_table([
        ('Identifiant du compte', bank_account.account_id),
        ('Gestionnaire', bank_account.manager_name),
    ])}
    {_btn('Se connecter à mon espace', bank_account.get_login_url(), bank.color_primary, bank.color_text_on_primary)}
    {_alert(
        'Utilisez votre identifiant et mot de passe habituels pour accéder à votre espace bancaire.',
        '#2ea44f', '#f6fff9', '#1a7a38'
    )}
    """

    _send_email(
        from_name=bank.name,
        to_email=bank_account.email,
        subject=f"{bank.name} — Votre compte est débloqué",
        html_body=_email_wrap(bank, body),
    )


# ── Email : changement de mot de passe ────────────────────────────────────

def send_password_changed_email(bank_account):
    from django.utils import timezone
    bank = bank_account.bank

    body = f"""
    <p style="font-size:16px;font-weight:700;color:#333333;margin:0 0 6px;font-family:Arial,Helvetica,sans-serif;">Bonjour {bank_account.first_name},</p>
    <p style="font-size:14px;color:#555555;line-height:1.7;margin:0 0 24px;">
      Le mot de passe de votre compte a été modifié le <strong>{timezone.now().strftime('%d/%m/%Y à %H:%M')}</strong>.
    </p>
    {_info_table([
        ('Identifiant', bank_account.account_id),
        ('Date de modification', timezone.now().strftime('%d/%m/%Y à %H:%M')),
    ])}
    {_btn('Se connecter à mon espace', bank_account.get_login_url(), bank.color_primary, bank.color_text_on_primary)}
    {_alert(
        f'Ce n\'était pas vous&nbsp;? Contactez immédiatement votre gestionnaire <strong>{bank_account.manager_name}</strong> pour sécuriser votre compte.',
        '#cc0000', '#fff8f8', '#cc0000'
    )}
    """

    _send_email(
        from_name=bank.name,
        to_email=bank_account.email,
        subject=f"{bank.name} — Modification de votre mot de passe",
        html_body=_email_wrap(bank, body),
    )


# ── PDF : helpers de base ──────────────────────────────────────────────────

def _hex_to_rgb(hex_color):
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4))


_HTTP_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (compatible; BankingPlatform/1.0; '
        '+https://mutuelspace.com)'
    )
}

# Cache module-level pour le reader du cachet (créé une seule fois par process)
_STAMP_READER_CACHE: ImageReader | None = None


def _make_stamp_reader() -> ImageReader | None:
    """
    Charge cachet.png (racine du projet), rend le fond blanc transparent,
    et met en cache le résultat pour éviter de recalculer à chaque PDF.
    """
    global _STAMP_READER_CACHE
    if _STAMP_READER_CACHE is not None:
        return _STAMP_READER_CACHE

    cachet_path = os.path.join(str(settings.BASE_DIR), 'cachet.png')
    if not os.path.exists(cachet_path):
        return None
    try:
        img = _PILImage.open(cachet_path).convert('RGBA')
        data = img.getdata()
        new_data = []
        for r, g, b, a in data:
            # Fond blanc/quasi-blanc → transparent
            if r > 230 and g > 230 and b > 230:
                new_data.append((r, g, b, 0))
            else:
                # Éléments du logo → légèrement transparents (effet cachet)
                new_data.append((r, g, b, int(a * 0.82)))
        img.putdata(new_data)
        out = io.BytesIO()
        img.save(out, format='PNG')
        out.seek(0)
        _STAMP_READER_CACHE = ImageReader(out)
        return _STAMP_READER_CACHE
    except Exception:
        return None


def _draw_image_stamp(canvas, cx, cy, w=60*mm, h=30*mm, tilt=-12):
    """
    Dessine cachet.png centré en (cx, cy), penché de `tilt` degrés.
    Fond blanc retiré (transparent), éléments CM semi-transparents.
    """
    reader = _make_stamp_reader()
    if not reader:
        return
    canvas.saveState()
    canvas.translate(cx, cy)
    canvas.rotate(tilt)
    canvas.drawImage(reader, -w / 2, -h / 2, width=w, height=h,
                     preserveAspectRatio=True, mask='auto')
    canvas.restoreState()


def _get_logo_reader(bank) -> ImageReader | None:
    """Retourne un ImageReader ReportLab pour le logo de la banque."""
    # Même priorité que effective_logo_url : logo_url > logo uploadé > favicon
    url = None
    if getattr(bank, 'logo_url', None):
        url = bank.logo_url
    elif bank.logo:
        try:
            url = bank.logo.url
        except Exception:
            pass
    if url and url.startswith('http'):
        try:
            resp = _requests.get(url, timeout=6, headers=_HTTP_HEADERS)
            if resp.status_code == 200:
                return ImageReader(io.BytesIO(resp.content))
        except Exception:
            pass
    # Fallback : fichier local
    if bank.logo:
        try:
            path = bank.logo.path
            if os.path.exists(path):
                return ImageReader(path)
        except Exception:
            pass
    return None


# ── PDF : mise en page ─────────────────────────────────────────────────────

def _page_bg(canvas, doc, bank, doc_type):
    """
    En-tête et pied de page professionnel pour tous les PDFs CM.
    Design : barre rouge CM + logo, bannière document, footer avec cachet image.
    """
    PAGE_W, PAGE_H = A4
    ML, MR = 20*mm, 20*mm

    primary  = _hex_to_rgb(bank.color_primary)
    navy     = (0.06, 0.11, 0.27)   # #0f1c45
    gray     = (0.38, 0.41, 0.46)
    light_bg = (0.975, 0.978, 0.984)
    white    = (1.0, 1.0, 1.0)

    canvas.saveState()

    # ════════════════════════════════════════════════════════════════
    # HEADER
    # ════════════════════════════════════════════════════════════════

    # 1. Barre rouge pleine en haut (6 mm)
    RED_H = 6 * mm
    canvas.setFillColorRGB(*primary)
    canvas.rect(0, PAGE_H - RED_H, PAGE_W, RED_H, stroke=0, fill=1)

    # 2. Zone header blanc cassé (38 mm)
    HEADER_H = 38 * mm
    header_top = PAGE_H - RED_H
    header_bot = header_top - HEADER_H
    canvas.setFillColorRGB(*light_bg)
    canvas.rect(0, header_bot, PAGE_W, HEADER_H, stroke=0, fill=1)

    # 3. Logo de la banque — colonne gauche
    logo_area_right = PAGE_W * 0.52
    logo_img = _get_logo_reader(bank)
    if logo_img:
        logo_x = ML
        logo_y = header_bot + (HEADER_H - 18 * mm) / 2
        try:
            canvas.drawImage(
                logo_img, logo_x, logo_y,
                width=70 * mm, height=18 * mm,
                preserveAspectRatio=True, anchor='sw', mask='auto',
            )
        except Exception:
            logo_img = None

    if not logo_img:
        # Fallback : boîte rouge + initiales
        bx, by, bs = ML, header_bot + HEADER_H / 2 - 6 * mm, 12 * mm
        canvas.setFillColorRGB(*primary)
        canvas.roundRect(bx, by, bs, bs, 2 * mm, stroke=0, fill=1)
        canvas.setFillColorRGB(*white)
        canvas.setFont('Helvetica-Bold', 9)
        canvas.drawCentredString(bx + bs / 2, by + 3.4 * mm, 'CM')
        canvas.setFillColorRGB(*primary)
        canvas.setFont('Helvetica-Bold', 13)
        canvas.drawString(bx + bs + 4 * mm, header_bot + HEADER_H / 2 + 1 * mm, bank.name)
        if bank.tagline:
            canvas.setFillColorRGB(*gray)
            canvas.setFont('Helvetica', 7)
            canvas.drawString(bx + bs + 4 * mm, header_bot + HEADER_H / 2 - 5 * mm, bank.tagline)

    # 4. Trait vertical séparateur (centre)
    sep_x = PAGE_W * 0.54
    canvas.setStrokeColorRGB(*primary)
    canvas.setLineWidth(0.8)
    canvas.line(sep_x, header_bot + 6 * mm, sep_x, header_bot + HEADER_H - 6 * mm)

    # 5. Infos banque — colonne droite (alignées droite)
    rx = PAGE_W - MR
    mid_y = header_bot + HEADER_H / 2

    canvas.setFillColorRGB(*primary)
    canvas.setFont('Helvetica-Bold', 9)
    canvas.drawRightString(rx, mid_y + 9 * mm, bank.name.upper())

    canvas.setFillColorRGB(*gray)
    canvas.setFont('Helvetica', 7.2)
    if bank.address:
        addr_line = bank.address.replace('\n', '  ·  ')[:55]
        canvas.drawRightString(rx, mid_y + 3.5 * mm, addr_line)
    if bank.phone:
        canvas.drawRightString(rx, mid_y - 1.5 * mm, f"Tél : {bank.phone}")
    if bank.email:
        canvas.drawRightString(rx, mid_y - 6 * mm, bank.email)
    if bank.swift:
        canvas.setFont('Helvetica-Bold', 6.5)
        canvas.setFillColorRGB(*primary)
        canvas.drawRightString(rx, mid_y - 10.5 * mm, f"SWIFT : {bank.swift}")

    # 6. Ligne rouge épaisse sous le header
    canvas.setStrokeColorRGB(*primary)
    canvas.setLineWidth(2.5)
    canvas.line(0, header_bot, PAGE_W, header_bot)

    # 7. Bannière type de document — fond navy (12 mm)
    DOC_H = 12 * mm
    doc_y  = header_bot - DOC_H
    canvas.setFillColorRGB(*navy)
    canvas.rect(0, doc_y, PAGE_W, DOC_H, stroke=0, fill=1)

    # Accent barre rouge gauche dans la bannière
    canvas.setFillColorRGB(*primary)
    canvas.rect(0, doc_y, 4 * mm, DOC_H, stroke=0, fill=1)

    # Texte du type de document
    canvas.setFillColorRGB(*white)
    canvas.setFont('Helvetica-Bold', 9.5)
    canvas.drawCentredString(PAGE_W / 2, doc_y + 3.8 * mm, doc_type)

    # Date en haut-droite de la bannière
    canvas.setFont('Helvetica', 7)
    canvas.setFillColorRGB(0.78, 0.82, 0.90)
    canvas.drawRightString(PAGE_W - MR, doc_y + 3.8 * mm,
                           datetime.now().strftime('%d/%m/%Y'))

    # ════════════════════════════════════════════════════════════════
    # FOOTER
    # ════════════════════════════════════════════════════════════════

    FOOTER_H = 36 * mm
    footer_top = FOOTER_H

    # Fond clair footer
    canvas.setFillColorRGB(*light_bg)
    canvas.rect(0, 0, PAGE_W, footer_top, stroke=0, fill=1)

    # Ligne rouge séparatrice
    canvas.setStrokeColorRGB(*primary)
    canvas.setLineWidth(1.5)
    canvas.line(0, footer_top, PAGE_W, footer_top)

    # Accent gauche footer (bande rouge verticale)
    canvas.setFillColorRGB(*primary)
    canvas.rect(0, 0, 4 * mm, footer_top, stroke=0, fill=1)

    # ── Texte footer gauche ────────────────────────────────────────
    tx = ML
    ty = footer_top - 8 * mm
    canvas.setFillColorRGB(*primary)
    canvas.setFont('Helvetica-Bold', 7.5)
    canvas.drawString(tx, ty, bank.name.upper())

    canvas.setFillColorRGB(*gray)
    canvas.setFont('Helvetica', 6.5)
    if bank.address:
        canvas.drawString(tx, ty - 5 * mm, bank.address.replace('\n', '  ·  ')[:70])
    contact_parts = []
    if bank.phone: contact_parts.append(f"☎ {bank.phone}")
    if bank.email: contact_parts.append(bank.email)
    if bank.swift: contact_parts.append(f"SWIFT : {bank.swift}")
    canvas.drawString(tx, ty - 10 * mm, '    '.join(contact_parts)[:75])

    # ── Mention légale centrée ─────────────────────────────────────
    canvas.setFont('Helvetica', 5.5)
    canvas.setFillColorRGB(0.62, 0.64, 0.68)
    canvas.drawCentredString(
        PAGE_W / 2, 5 * mm,
        "Document officiel — Crédit Mutuel. Ne constitue pas un contrat sans signature manuscrite."
    )

    # ── Cachet image CM — bas droite, penché ──────────────────────
    stamp_cx = PAGE_W - MR - 28 * mm
    stamp_cy = footer_top / 2
    _draw_image_stamp(canvas, stamp_cx, stamp_cy, w=62 * mm, h=30 * mm, tilt=-13)

    canvas.restoreState()


# ── PDF : tableau d'informations ───────────────────────────────────────────

_LABEL_STYLE = ParagraphStyle(
    'InfoLabel',
    fontName='Helvetica-Bold',
    fontSize=8,
    textColor=colors.HexColor('#1a3a5c'),
    leading=11,
    wordWrap='LTR',
)
_VALUE_STYLE = ParagraphStyle(
    'InfoValue',
    fontName='Helvetica',
    fontSize=8.5,
    textColor=colors.HexColor('#1f2937'),
    leading=12,
    wordWrap='LTR',
)
_VALUE_MONO_STYLE = ParagraphStyle(
    'InfoValueMono',
    fontName='Courier',
    fontSize=8,
    textColor=colors.HexColor('#1f2937'),
    leading=11,
    wordWrap='LTR',
)


def _wrap_cell(value, mono=False):
    """Convertit une valeur en Paragraph pour garantir le retour à la ligne."""
    if isinstance(value, Paragraph):
        return value
    style = _VALUE_MONO_STYLE if mono else _VALUE_STYLE
    return Paragraph(str(value) if value is not None else '—', style)


def _build_info_table(data, primary, col_widths=None):
    """
    Tableau label/valeur avec retour à la ligne automatique sur les valeurs longues.
    Les chaînes IBAN/codes sont détectées et affichées en police monospace.
    """
    if col_widths is None:
        col_widths = [58 * mm, 112 * mm]

    _iban_keywords = {'iban', 'rib', 'bic', 'swift', 'code'}

    wrapped = []
    for row in data:
        label = row[0]
        value = row[1] if len(row) > 1 else ''
        # Détection IBAN/code : affichage monospace
        is_mono = any(k in str(label).lower() for k in _iban_keywords)
        wrapped.append([
            Paragraph(str(label), _LABEL_STYLE),
            _wrap_cell(value, mono=is_mono),
        ])

    table = Table(wrapped, colWidths=col_widths)
    table.setStyle(TableStyle([
        # Colonne label (gauche) — fond bleuté
        ('BACKGROUND',    (0, 0), (0, -1), colors.HexColor('#f0f4f9')),
        ('LINEBELOW',     (0, 0), (-1, -2), 0.3, colors.HexColor('#dde3ed')),
        ('BOX',           (0, 0), (-1, -1), 0.6, colors.HexColor('#c8d4e4')),
        ('LINEBEFORE',    (1, 0), (1, -1),  0.3, colors.HexColor('#dde3ed')),
        # Alternance sur la colonne valeur
        ('ROWBACKGROUNDS', (1, 0), (1, -1), [colors.white, colors.HexColor('#f9fafb')]),
        # Padding généreux pour éviter les débordements
        ('TOPPADDING',    (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING',   (0, 0), (-1, -1), 9),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return table


def _section_header(label, primary_color):
    """Titre de section avec barre colorée gauche."""
    return Paragraph(
        f'<b>{label}</b>',
        ParagraphStyle(
            'SectionHeader',
            fontSize=9,
            fontName='Helvetica-Bold',
            textColor=primary_color,
            spaceBefore=10,
            spaceAfter=4,
            leftIndent=8,
            borderPad=4,
        )
    )


# ── PDF RIB ────────────────────────────────────────────────────────────────

def generate_rib_pdf(bank_account, all_accounts=None):
    buffer = io.BytesIO()
    bank = bank_account.bank
    primary = colors.HexColor(bank.color_primary)
    # Marges 18 mm → contenu 174 mm
    ML = MR = 18 * mm
    CONTENT_W = 210 * mm - ML - MR   # 174 mm

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=60 * mm, bottomMargin=44 * mm,
        leftMargin=ML, rightMargin=MR,
    )
    story = []
    page_fn = lambda c, d: _page_bg(c, d, bank, "RELEVÉ D'IDENTITÉ BANCAIRE (RIB)")

    story.append(Spacer(1, 4 * mm))

    # ── Titulaire + banque (pleine largeur, une seule table) ───────
    # Utilise la pleine largeur pour éviter tout débordement
    common_data = [
        ['Titulaire du compte', bank_account.get_full_name()],
        ['Domiciliation',       bank.name],
        ['Adresse banque',      (bank.address or '').replace('\n', '  ·  ')],
        ['BIC / SWIFT',         bank_account.bank_swift or bank.swift or '—'],
        ['Pays',                bank_account.country],
        ['Devise',              bank_account.currency],
    ]
    # label=52 mm, valeur=122 mm → total 174 mm = CONTENT_W
    story.append(_build_info_table(common_data, primary, [52 * mm, CONTENT_W - 52 * mm]))
    story.append(Spacer(1, 8 * mm))

    # ── Coordonnées IBAN par compte ────────────────────────────────
    accounts_to_show = all_accounts if (all_accounts and len(all_accounts) > 1) else [bank_account]
    for acc in accounts_to_show:
        story.append(_section_header(acc.get_account_type_display().upper(), primary))

        # IBAN formaté en groupes de 4 — bloc centré pleine largeur
        iban_fmt = ' '.join(acc.rib[i:i+4] for i in range(0, len(acc.rib), 4))
        iban_block = Table(
            [[Paragraph(
                f'<font name="Courier-Bold" size="12">{iban_fmt}</font>',
                ParagraphStyle('IBAN', alignment=TA_CENTER, leading=16),
            )]],
            colWidths=[CONTENT_W],
        )
        iban_block.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#eef4fb')),
            ('BOX',           (0, 0), (-1, -1), 1.5, primary),
            ('TOPPADDING',    (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('LEFTPADDING',   (0, 0), (-1, -1), 10),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
        ]))
        story.append(iban_block)
        story.append(Spacer(1, 4 * mm))

        # Détail RIB sur 2 colonnes côte à côte
        rib_left  = [['Code banque',  acc.rib_code_banque or '—'],
                     ['Code guichet', acc.rib_code_guichet or '—']]
        rib_right = [['N° de compte', acc.rib_numero_compte or '—'],
                     ['Clé RIB',      acc.rib_cle or '—']]
        half = CONTENT_W / 2 - 2 * mm
        rib_row = Table(
            [[_build_info_table(rib_left,  primary, [28 * mm, half - 28 * mm]),
              _build_info_table(rib_right, primary, [28 * mm, half - 28 * mm])]],
            colWidths=[half, half],
        )
        rib_row.setStyle(TableStyle([
            ('LEFTPADDING',   (0, 0), (-1, -1), 0),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
            ('TOPPADDING',    (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING',   (1, 0), (1, -1),  4 * mm),
        ]))
        story.append(rib_row)
        story.append(Spacer(1, 5 * mm))

    # ── Certification ──────────────────────────────────────────────
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        f"Je soussigné(e) certifie que les coordonnées bancaires figurant sur ce document "
        f"sont exactes et correspondent à mon/mes compte(s) ouvert(s) auprès de "
        f"<b>{bank.name}</b>.",
        ParagraphStyle(
            'Cert', fontSize=8.5, leading=14,
            textColor=colors.HexColor('#374151'),
            borderWidth=0.6, borderColor=colors.HexColor('#cbd5e1'),
            borderPad=10, backColor=colors.HexColor('#f8fafc'),
        ),
    ))

    doc.build(story, onFirstPage=page_fn, onLaterPages=page_fn)
    buffer.seek(0)
    return buffer


# ── PDF Bordereau de virement ──────────────────────────────────────────────

def generate_transfer_slip_pdf(transaction):
    buffer = io.BytesIO()
    bank = transaction.account.bank
    primary   = colors.HexColor(bank.color_primary)
    ML = MR   = 18 * mm
    CONTENT_W = 210 * mm - ML - MR   # 174 mm

    STATUS_CONFIG = {
        'pending':   ('#fffbeb', '#92400e', '#f59e0b', 'EN COURS DE VALIDATION'),
        'validated': ('#f0fdf4', '#166534', '#22c55e', 'VIREMENT VALIDÉ'),
        'rejected':  ('#fef2f2', '#991b1b', '#ef4444', 'VIREMENT REJETÉ'),
    }
    s_bg, s_fg, s_border, s_label = STATUS_CONFIG.get(
        transaction.status,
        ('#f3f4f6', '#374151', '#9ca3af', transaction.status.upper())
    )

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=60 * mm, bottomMargin=44 * mm,
        leftMargin=ML, rightMargin=MR,
    )
    story = []
    page_fn = lambda c, d: _page_bg(c, d, bank, "BORDEREAU DE VIREMENT")

    story.append(Spacer(1, 5 * mm))

    # ── Badge statut ───────────────────────────────────────────────
    story.append(Table(
        [[Paragraph(
            f'<font name="Helvetica-Bold" size="11" color="{s_fg}">{s_label}</font>',
            ParagraphStyle('St', alignment=TA_CENTER),
        )]],
        colWidths=[CONTENT_W],
        style=TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor(s_bg)),
            ('BOX',           (0, 0), (-1, -1), 1.8, colors.HexColor(s_border)),
            ('TOPPADDING',    (0, 0), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 11),
            ('LEFTPADDING',   (0, 0), (-1, -1), 10),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
        ]),
    ))
    story.append(Spacer(1, 6 * mm))

    # ── Montant mis en évidence ────────────────────────────────────
    sign  = '−' if transaction.is_debit else '+'
    amt_color = '#dc2626' if transaction.is_debit else '#16a34a'
    story.append(Table(
        [[Paragraph(
            f'<font name="Helvetica-Bold" size="20" color="{amt_color}">'
            f'{sign} {transaction.amount:,.2f} {transaction.currency}</font>',
            ParagraphStyle('Amt', alignment=TA_CENTER),
        )]],
        colWidths=[CONTENT_W],
        style=TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('BOX',           (0, 0), (-1, -1), 0.4, colors.HexColor('#e2e8f0')),
            ('TOPPADDING',    (0, 0), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 11),
        ]),
    ))
    story.append(Spacer(1, 7 * mm))

    # ── Donneur d'ordre + Bénéficiaire (pleine largeur, l'un après l'autre) ─
    # On évite les 2 colonnes qui débordent — on utilise 2 tables séquentielles
    benef_iban = (
        transaction.beneficiary.account_number
        if transaction.beneficiary else transaction.beneficiary_iban
    ) or '—'
    benef_name = transaction.get_beneficiary_display_name()
    benef_bank = (
        transaction.beneficiary.bank_name
        if transaction.beneficiary else transaction.beneficiary_bank
    ) or '—'

    # Label column = 48 mm, valeur = CONTENT_W - 48 mm
    LW = 48 * mm
    VW = CONTENT_W - LW

    story.append(_section_header("DONNEUR D'ORDRE", primary))
    story.append(_build_info_table([
        ['Nom',  transaction.account.get_full_name()],
        ['IBAN', transaction.account.rib],
    ], primary, [LW, VW]))

    story.append(Spacer(1, 5 * mm))
    story.append(_section_header('BÉNÉFICIAIRE', primary))
    story.append(_build_info_table([
        ['Nom',   benef_name],
        ['IBAN',  benef_iban],
        ['Banque', benef_bank],
    ], primary, [LW, VW]))

    story.append(Spacer(1, 7 * mm))

    # ── Détails de l'opération ─────────────────────────────────────
    story.append(_section_header("DÉTAILS DE L'OPÉRATION", primary))
    detail_data = [
        ['Référence',          transaction.reference],
        ['Type',               transaction.get_transaction_type_display()],
        ["Date d'initiation",  transaction.created_at.strftime('%d/%m/%Y  %H:%M')],
        ['Motif / Libellé',    transaction.description or '—'],
    ]
    if transaction.status == 'validated' and transaction.validated_at:
        detail_data.append(['Date de validation', transaction.validated_at.strftime('%d/%m/%Y  %H:%M')])
    if transaction.status == 'rejected':
        if transaction.validated_at:
            detail_data.append(['Date de rejet', transaction.validated_at.strftime('%d/%m/%Y  %H:%M')])
        detail_data.append(['Motif du rejet', transaction.rejection_reason or '—'])
        if transaction.rejection_fee:
            detail_data.append(['Frais de redirection',
                                 f"{transaction.rejection_fee:,.2f} {transaction.currency}"])

    story.append(_build_info_table(detail_data, primary, [LW, VW]))

    doc.build(story, onFirstPage=page_fn, onLaterPages=page_fn)
    buffer.seek(0)
    return buffer


# ── PDF Relevé de compte ───────────────────────────────────────────────────

def generate_statement_pdf(bank_account, transactions, date_from, date_to):
    buffer = io.BytesIO()
    bank = bank_account.bank
    primary = colors.HexColor(bank.color_primary)
    ML = MR  = 12 * mm
    CONTENT_W = 210 * mm - ML - MR   # 186 mm

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=60 * mm, bottomMargin=44 * mm,
        leftMargin=ML, rightMargin=MR,
    )
    story = []
    period = f"Période : {date_from.strftime('%d/%m/%Y')} → {date_to.strftime('%d/%m/%Y')}"
    page_fn = lambda c, d: _page_bg(c, d, bank, f"RELEVÉ DE COMPTE  ·  {period}")

    story.append(Spacer(1, 4 * mm))

    # ── Carte compte ───────────────────────────────────────────────
    iban_fmt = ' '.join(bank_account.rib[i:i+4] for i in range(0, len(bank_account.rib), 4))
    # 2 colonnes : nom à gauche (60%), IBAN à droite (40%)
    col_name = CONTENT_W * 0.45
    col_iban = CONTENT_W * 0.55
    acct_tbl = Table(
        [[Paragraph(
              f'<font name="Helvetica-Bold" size="10">{bank_account.get_full_name()}</font><br/>'
              f'<font name="Helvetica" size="7.5" color="#64748b">{bank_account.get_account_type_display()}</font>',
              ParagraphStyle('AN', leading=14, spaceAfter=0),
          ),
          Paragraph(
              f'<font name="Helvetica" size="7" color="#64748b">IBAN</font><br/>'
              f'<font name="Courier-Bold" size="8.5">{iban_fmt}</font>',
              ParagraphStyle('AI', alignment=TA_RIGHT, leading=13, spaceAfter=0),
          )]],
        colWidths=[col_name, col_iban],
    )
    acct_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#eef4fb')),
        ('BOX',           (0, 0), (-1, -1), 0.8, primary),
        ('LINEBEFORE',    (1, 0), (1, -1),  0.5, colors.HexColor('#c8d4e4')),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(acct_tbl)
    story.append(Spacer(1, 6 * mm))

    # ── Tableau des transactions ───────────────────────────────────
    story.append(_section_header('MOUVEMENTS DU COMPTE', primary))

    # Styles pour cellules Paragraph dans le tableau
    _th = ParagraphStyle('TH', fontName='Helvetica-Bold', fontSize=7.5,
                         textColor=colors.white, leading=10, wordWrap='LTR')
    _td = ParagraphStyle('TD', fontName='Helvetica', fontSize=7.5,
                         textColor=colors.HexColor('#1f2937'), leading=10, wordWrap='LTR')
    _td_mono = ParagraphStyle('TDm', fontName='Courier', fontSize=7,
                               textColor=colors.HexColor('#374151'), leading=10, wordWrap='LTR')
    _td_debit  = ParagraphStyle('TDd', fontName='Helvetica-Bold', fontSize=7.5,
                                 textColor=colors.HexColor('#dc2626'), leading=10,
                                 alignment=TA_RIGHT, wordWrap='LTR')
    _td_credit = ParagraphStyle('TDc', fontName='Helvetica-Bold', fontSize=7.5,
                                 textColor=colors.HexColor('#16a34a'), leading=10,
                                 alignment=TA_RIGHT, wordWrap='LTR')
    _td_right  = ParagraphStyle('TDr', fontName='Helvetica', fontSize=7.5,
                                 textColor=colors.HexColor('#1f2937'), leading=10,
                                 alignment=TA_RIGHT, wordWrap='LTR')

    # Colonnes : Date | Référence | Libellé | Débit | Crédit | Statut
    # 186mm total : 20+28+76+22+22+18 = 186 mm
    col_w = [20 * mm, 28 * mm, 76 * mm, 22 * mm, 22 * mm, 18 * mm]

    header_row = [Paragraph(h, _th) for h in
                  ['Date', 'Référence', 'Libellé / Description', 'Débit', 'Crédit', 'Statut']]
    rows = [header_row]

    total_debit  = 0.0
    total_credit = 0.0

    for txn in transactions:
        desc = (txn.description or txn.get_transaction_type_display())[:55]
        if txn.is_debit:
            debit_cell  = Paragraph(f"{txn.amount:,.2f}", _td_debit)
            credit_cell = Paragraph('', _td)
            total_debit += float(txn.amount)
        else:
            debit_cell  = Paragraph('', _td)
            credit_cell = Paragraph(f"{txn.amount:,.2f}", _td_credit)
            total_credit += float(txn.amount)

        rows.append([
            Paragraph(txn.created_at.strftime('%d/%m/%Y'), _td),
            Paragraph(txn.reference, _td_mono),
            Paragraph(desc, _td),
            debit_cell,
            credit_cell,
            Paragraph(txn.get_status_display(), _td),
        ])

    # Ligne totaux
    _td_tot = ParagraphStyle('Tot', fontName='Helvetica-Bold', fontSize=8,
                              textColor=colors.HexColor('#1a3a5c'), leading=11,
                              alignment=TA_RIGHT)
    rows.append([
        Paragraph('', _td), Paragraph('', _td),
        Paragraph('<b>TOTAL PÉRIODE</b>',
                  ParagraphStyle('TotL', fontName='Helvetica-Bold', fontSize=8,
                                 textColor=colors.HexColor('#1a3a5c'), leading=11)),
        Paragraph(f"{total_debit:,.2f}", _td_debit),
        Paragraph(f"{total_credit:,.2f}", _td_credit),
        Paragraph('', _td),
    ])

    n = len(rows)
    txn_table = Table(rows, colWidths=col_w, repeatRows=1)
    txn_table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0),   (-1, 0),   primary),
        ('ROWBACKGROUNDS',(0, 1),   (-1, n-2), [colors.white, colors.HexColor('#f8fafc')]),
        ('BACKGROUND',    (0, n-1), (-1, n-1), colors.HexColor('#eef4fb')),
        ('LINEABOVE',     (0, n-1), (-1, n-1), 1.2, primary),
        ('GRID',          (0, 0),   (-1, -1),  0.25, colors.HexColor('#dde3ed')),
        ('TOPPADDING',    (0, 0),   (-1, -1),  5),
        ('BOTTOMPADDING', (0, 0),   (-1, -1),  5),
        ('LEFTPADDING',   (0, 0),   (-1, -1),  4),
        ('RIGHTPADDING',  (0, 0),   (-1, -1),  4),
        ('VALIGN',        (0, 0),   (-1, -1),  'TOP'),
    ]))
    story.append(txn_table)
    story.append(Spacer(1, 6 * mm))

    # ── Solde final ────────────────────────────────────────────────
    bal_color = '#16a34a' if bank_account.balance >= 0 else '#dc2626'
    balance_tbl = Table(
        [[Paragraph(
              f'<font name="Helvetica" size="8" color="#64748b">'
              f'Solde au {date_to.strftime("%d/%m/%Y")}</font>',
              ParagraphStyle('BL', alignment=TA_RIGHT, leading=12),
          ),
          Paragraph(
              f'<font name="Helvetica-Bold" size="13" color="{bal_color}">'
              f'{bank_account.balance:,.2f} {bank_account.currency}</font>',
              ParagraphStyle('BV', alignment=TA_RIGHT, leading=16),
          )]],
        colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45],
    )
    balance_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX',           (0, 0), (-1, -1), 0.8, primary),
        ('LINEBEFORE',    (1, 0), (1, -1),  0.5, colors.HexColor('#c8d4e4')),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(balance_tbl)

    doc.build(story, onFirstPage=page_fn, onLaterPages=page_fn)
    buffer.seek(0)
    return buffer
