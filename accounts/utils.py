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


# URL du cachet officiel CM (image réelle — non générée)
_CM_STAMP_URL = (
    "https://cdnwmsi.e-i.com/SITW/wm/global/1.0.0/af/assets/articles/"
    "CERT-euro-information/cm_hero-article.jpg?1"
)
_CM_STAMP_CACHE: bytes | None = None


def _get_stamp_bytes() -> bytes | None:
    """Télécharge et met en cache l'image de cachet CM."""
    global _CM_STAMP_CACHE
    if _CM_STAMP_CACHE is not None:
        return _CM_STAMP_CACHE
    try:
        resp = _requests.get(_CM_STAMP_URL, timeout=8)
        if resp.status_code == 200:
            _CM_STAMP_CACHE = resp.content
            return _CM_STAMP_CACHE
    except Exception:
        pass
    return None


def _make_stamp_reader(alpha: int = 180) -> ImageReader | None:
    """
    Retourne un ImageReader ReportLab pour le cachet CM.
    alpha : opacité 0-255 (180 ≃ 70 % opaque → effet cachet semi-transparent).
    """
    raw = _get_stamp_bytes()
    if not raw:
        return None
    try:
        img = _PILImage.open(io.BytesIO(raw)).convert('RGBA')
        r, g, b, a = img.split()
        a = a.point(lambda p: min(p, alpha))
        img = _PILImage.merge('RGBA', (r, g, b, a))
        out = io.BytesIO()
        img.save(out, format='PNG')
        out.seek(0)
        return ImageReader(out)
    except Exception:
        return None


def _draw_image_stamp(canvas, cx, cy, w=58*mm, h=29*mm, tilt=-13):
    """
    Dessine le cachet CM (image réelle) centré en (cx, cy), penché de `tilt` degrés.
    """
    reader = _make_stamp_reader(alpha=175)
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
    # Priorité 1 : bank.logo (Supabase)
    url = None
    if bank.logo:
        try:
            url = bank.logo.url
        except Exception:
            pass
    # Priorité 2 : favicon_url externe
    if not url and bank.favicon_url:
        url = bank.favicon_url
    if url and url.startswith('http'):
        try:
            resp = _requests.get(url, timeout=6)
            if resp.status_code == 200:
                return ImageReader(io.BytesIO(resp.content))
        except Exception:
            pass
    # Priorité 3 : chemin local
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

def _build_info_table(data, primary, col_widths=None):
    if col_widths is None:
        col_widths = [62 * mm, 108 * mm]
    table = Table(data, colWidths=col_widths)
    table.setStyle(TableStyle([
        # Colonne label (gauche)
        ('BACKGROUND',    (0, 0), (0, -1), colors.HexColor('#f3f6fa')),
        ('TEXTCOLOR',     (0, 0), (0, -1), colors.HexColor('#1a3a5c')),
        ('FONTNAME',      (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (0, -1), 8.5),
        # Colonne valeur (droite)
        ('FONTNAME',      (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE',      (1, 0), (1, -1), 9),
        ('TEXTCOLOR',     (1, 0), (1, -1), colors.HexColor('#1f2937')),
        # Alternance légère
        ('ROWBACKGROUNDS', (1, 0), (1, -1), [colors.white, colors.HexColor('#fafbfc')]),
        # Bordures
        ('LINEBELOW',     (0, 0), (-1, -2), 0.35, colors.HexColor('#e2e8f0')),
        ('BOX',           (0, 0), (-1, -1), 0.6,  colors.HexColor('#cbd5e1')),
        ('LINEBEFORE',    (1, 0), (1, -1),  0.35, colors.HexColor('#e2e8f0')),
        # Padding
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING',   (0, 0), (-1, -1), 11),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
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
    CONTENT_W = 170 * mm

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=60 * mm, bottomMargin=44 * mm,
        leftMargin=20 * mm, rightMargin=20 * mm,
    )
    story = []
    page_fn = lambda c, d: _page_bg(c, d, bank, "RELEVÉ D'IDENTITÉ BANCAIRE (RIB)")

    story.append(Spacer(1, 4 * mm))

    # ── Titulaire + banque en deux colonnes ────────────────────────
    col_l = 82 * mm
    col_r = 82 * mm
    gap   = 6 * mm

    holder_data = [
        ['Titulaire', bank_account.get_full_name()],
        ['Pays',      bank_account.country],
        ['Devise',    bank_account.currency],
    ]
    bank_data = [
        ['Domiciliation', bank.name],
        ['Adresse',       (bank.address or '').replace('\n', ' ')[:40]],
        ['BIC / SWIFT',   bank_account.bank_swift or bank.swift or '—'],
    ]

    two_col = Table(
        [[_build_info_table(holder_data, primary, [32 * mm, 46 * mm]),
          _build_info_table(bank_data,   primary, [32 * mm, 46 * mm])]],
        colWidths=[col_l, col_r],
        hAlign='LEFT',
    )
    two_col.setStyle(TableStyle([
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING',   (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
        ('LEFTPADDING',  (1, 0), (1, -1),  gap),
    ]))
    story.append(two_col)
    story.append(Spacer(1, 8 * mm))

    # ── Coordonnées IBAN par compte ────────────────────────────────
    accounts_to_show = all_accounts if (all_accounts and len(all_accounts) > 1) else [bank_account]
    for acc in accounts_to_show:
        story.append(_section_header(acc.get_account_type_display().upper(), primary))

        iban_fmt = ' '.join(acc.rib[i:i+4] for i in range(0, len(acc.rib), 4))

        # IBAN mis en valeur dans un bloc
        iban_block = Table(
            [[Paragraph(f'<font name="Helvetica-Bold" size="13">{iban_fmt}</font>',
                        ParagraphStyle('IBAN', alignment=TA_CENTER, spaceAfter=0))]],
            colWidths=[CONTENT_W],
        )
        iban_block.setStyle(TableStyle([
            ('BACKGROUND',     (0, 0), (-1, -1), colors.HexColor('#eef4fb')),
            ('BOX',            (0, 0), (-1, -1), 1.2, primary),
            ('TOPPADDING',     (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING',  (0, 0), (-1, -1), 10),
        ]))
        story.append(iban_block)
        story.append(Spacer(1, 4 * mm))

        rib_data = [
            ['Code banque',  acc.rib_code_banque or '—'],
            ['Code guichet', acc.rib_code_guichet or '—'],
            ['N° de compte', acc.rib_numero_compte or '—'],
            ['Clé RIB',      acc.rib_cle or '—'],
        ]
        story.append(_build_info_table(rib_data, primary))
        story.append(Spacer(1, 5 * mm))

    # ── Certification ──────────────────────────────────────────────
    story.append(Spacer(1, 4 * mm))
    cert_style = ParagraphStyle(
        'Cert', fontSize=8.5, leading=14,
        textColor=colors.HexColor('#374151'),
        borderWidth=0.6, borderColor=colors.HexColor('#cbd5e1'),
        borderPad=8, backColor=colors.HexColor('#f8fafc'),
        spaceAfter=0,
    )
    story.append(Paragraph(
        f"Je soussigné(e) certifie que les coordonnées bancaires figurant sur ce document "
        f"sont exactes et correspondent à mon/mes compte(s) ouvert(s) auprès de "
        f"<b>{bank.name}</b>.",
        cert_style,
    ))

    doc.build(story, onFirstPage=page_fn, onLaterPages=page_fn)
    buffer.seek(0)
    return buffer


# ── PDF Bordereau de virement ──────────────────────────────────────────────

def generate_transfer_slip_pdf(transaction):
    buffer = io.BytesIO()
    bank = transaction.account.bank
    primary      = colors.HexColor(bank.color_primary)
    primary_rgb  = _hex_to_rgb(bank.color_primary)
    CONTENT_W    = 170 * mm

    STATUS_CONFIG = {
        'pending':   ('#fffbeb', '#92400e', '#f59e0b', 'EN COURS DE VALIDATION', '⏳'),
        'validated': ('#f0fdf4', '#166534', '#22c55e', 'VALIDÉ',                 '✓'),
        'rejected':  ('#fef2f2', '#991b1b', '#ef4444', 'REJETÉ',                 '✕'),
    }
    s_bg, s_fg, s_border, s_label, s_icon = STATUS_CONFIG.get(
        transaction.status,
        ('#f3f4f6', '#374151', '#9ca3af', transaction.status.upper(), '●')
    )

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=60 * mm, bottomMargin=44 * mm,
        leftMargin=20 * mm, rightMargin=20 * mm,
    )
    story = []
    page_fn = lambda c, d: _page_bg(c, d, bank, "BORDEREAU DE VIREMENT")

    story.append(Spacer(1, 5 * mm))

    # ── Badge statut ───────────────────────────────────────────────
    status_tbl = Table(
        [[Paragraph(
            f'<font name="Helvetica-Bold" size="12" color="{s_fg}">'
            f'{s_icon}  {s_label}</font>',
            ParagraphStyle('St', alignment=TA_CENTER),
        )]],
        colWidths=[CONTENT_W],
    )
    status_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor(s_bg)),
        ('BOX',           (0, 0), (-1, -1), 1.8, colors.HexColor(s_border)),
        ('TOPPADDING',    (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(status_tbl)
    story.append(Spacer(1, 7 * mm))

    # ── Montant mis en évidence ────────────────────────────────────
    sign  = '−' if transaction.is_debit else '+'
    color = '#dc2626' if transaction.is_debit else '#16a34a'
    amount_tbl = Table(
        [[Paragraph(
            f'<font name="Helvetica-Bold" size="22" color="{color}">'
            f'{sign} {transaction.amount:,.2f} {transaction.currency}</font>',
            ParagraphStyle('Amt', alignment=TA_CENTER),
        )]],
        colWidths=[CONTENT_W],
    )
    amount_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX',           (0, 0), (-1, -1), 0.4, colors.HexColor('#e2e8f0')),
        ('TOPPADDING',    (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(amount_tbl)
    story.append(Spacer(1, 7 * mm))

    # ── Parties : Donneur d'ordre | Bénéficiaire ───────────────────
    benef_iban = (
        transaction.beneficiary.account_number
        if transaction.beneficiary else transaction.beneficiary_iban
    ) or '—'
    benef_name = transaction.get_beneficiary_display_name()
    benef_bank = (
        transaction.beneficiary.bank_name
        if transaction.beneficiary else transaction.beneficiary_bank
    ) or '—'

    col = 82 * mm
    gap = 6 * mm
    parties = Table(
        [[_build_info_table(
              [['Donneur d\'ordre', transaction.account.get_full_name()],
               ['IBAN',            transaction.account.rib]],
              primary, [30 * mm, 48 * mm],
          ),
          _build_info_table(
              [['Bénéficiaire',    benef_name],
               ['IBAN',            benef_iban],
               ['Banque',          benef_bank]],
              primary, [28 * mm, 50 * mm],
          )]],
        colWidths=[col, col],
    )
    parties.setStyle(TableStyle([
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING',   (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
        ('LEFTPADDING',  (1, 0), (1, -1),  gap),
    ]))
    story.append(parties)
    story.append(Spacer(1, 7 * mm))

    # ── Détails du virement ────────────────────────────────────────
    story.append(_section_header('DÉTAILS DE L\'OPÉRATION', primary))
    detail_data = [
        ['Référence',       transaction.reference],
        ['Type',            transaction.get_transaction_type_display()],
        ['Date d\'initiation', transaction.created_at.strftime('%d/%m/%Y  %H:%M')],
        ['Motif / Libellé', transaction.description or '—'],
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

    story.append(_build_info_table(detail_data, primary))

    doc.build(story, onFirstPage=page_fn, onLaterPages=page_fn)
    buffer.seek(0)
    return buffer


# ── PDF Relevé de compte ───────────────────────────────────────────────────

def generate_statement_pdf(bank_account, transactions, date_from, date_to):
    buffer = io.BytesIO()
    bank = bank_account.bank
    primary = colors.HexColor(bank.color_primary)
    CONTENT_W = 180 * mm

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=60 * mm, bottomMargin=44 * mm,
        leftMargin=15 * mm, rightMargin=15 * mm,
    )
    story = []
    period = f"Période : {date_from.strftime('%d/%m/%Y')} → {date_to.strftime('%d/%m/%Y')}"
    page_fn = lambda c, d: _page_bg(c, d, bank, f"RELEVÉ DE COMPTE  ·  {period}")

    story.append(Spacer(1, 4 * mm))

    # ── Carte compte ───────────────────────────────────────────────
    iban_fmt = ' '.join(bank_account.rib[i:i+4] for i in range(0, len(bank_account.rib), 4))
    acct_tbl = Table(
        [[Paragraph(
            f'<b><font size="9">{bank_account.get_full_name()}</font></b>',
            ParagraphStyle('AN', spaceAfter=0, spaceBefore=0),
          ),
          Paragraph(
            f'<font name="Helvetica" size="7.5" color="#64748b">IBAN</font><br/>'
            f'<font name="Helvetica-Bold" size="9">{iban_fmt}</font>',
            ParagraphStyle('AI', alignment=TA_RIGHT, spaceAfter=0),
          )]],
        colWidths=[90 * mm, 90 * mm],
    )
    acct_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#eef4fb')),
        ('BOX',           (0, 0), (-1, -1), 0.8, primary),
        ('LINEBEFORE',    (1, 0), (1, -1),  0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING',   (0, 0), (-1, -1), 12),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 12),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(acct_tbl)
    story.append(Spacer(1, 6 * mm))

    # ── Tableau des transactions ───────────────────────────────────
    story.append(_section_header('MOUVEMENTS DU COMPTE', primary))

    headers = ['Date', 'Référence', 'Libellé / Description', 'Débit', 'Crédit', 'Statut']
    rows = [headers]
    total_debit  = 0.0
    total_credit = 0.0

    for txn in transactions:
        if txn.is_debit:
            debit  = f"{txn.amount:,.2f}"
            credit = ''
            total_debit += float(txn.amount)
        else:
            debit  = ''
            credit = f"{txn.amount:,.2f}"
            total_credit += float(txn.amount)

        rows.append([
            txn.created_at.strftime('%d/%m/%Y'),
            txn.reference,
            (txn.description or txn.get_transaction_type_display())[:40],
            debit,
            credit,
            txn.get_status_display(),
        ])

    # Ligne totaux
    rows.append(['', '', 'TOTAL PÉRIODE', f"{total_debit:,.2f}", f"{total_credit:,.2f}", ''])

    col_w = [22 * mm, 30 * mm, 66 * mm, 22 * mm, 22 * mm, 18 * mm]
    txn_table = Table(rows, colWidths=col_w, repeatRows=1)

    debit_rows  = [i + 1 for i, r in enumerate(rows[1:]) if r[3] and r[3] != f"{total_debit:,.2f}"]
    credit_rows = [i + 1 for i, r in enumerate(rows[1:]) if r[4] and r[4] != f"{total_credit:,.2f}"]
    n = len(rows)

    cmd = [
        # En-tête
        ('BACKGROUND',    (0, 0),  (-1, 0),   primary),
        ('TEXTCOLOR',     (0, 0),  (-1, 0),   colors.white),
        ('FONTNAME',      (0, 0),  (-1, 0),   'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0),  (-1, 0),   7.5),
        # Corps
        ('FONTSIZE',      (0, 1),  (-1, -1),  7.8),
        ('FONTNAME',      (0, 1),  (-1, -1),  'Helvetica'),
        ('ROWBACKGROUNDS',(0, 1),  (-1, n-2), [colors.white, colors.HexColor('#f8fafc')]),
        ('GRID',          (0, 0),  (-1, -1),  0.25, colors.HexColor('#e2e8f0')),
        # Padding
        ('TOPPADDING',    (0, 0),  (-1, -1),  5),
        ('BOTTOMPADDING', (0, 0),  (-1, -1),  5),
        ('LEFTPADDING',   (0, 0),  (-1, -1),  5),
        ('RIGHTPADDING',  (0, 0),  (-1, -1),  5),
        # Alignement montants
        ('ALIGN',         (3, 0),  (4, -1),   'RIGHT'),
        ('FONTNAME',      (3, 0),  (4, -1),   'Helvetica'),
        # Ligne totaux
        ('BACKGROUND',    (0, n-1),(-1, n-1), colors.HexColor('#eef4fb')),
        ('FONTNAME',      (0, n-1),(-1, n-1), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, n-1),(-1, n-1), 8),
        ('LINEABOVE',     (0, n-1),(-1, n-1), 1.2, primary),
    ]
    for r in debit_rows:
        cmd.append(('TEXTCOLOR', (3, r), (3, r), colors.HexColor('#dc2626')))
        cmd.append(('FONTNAME',  (3, r), (3, r), 'Helvetica-Bold'))
    for r in credit_rows:
        cmd.append(('TEXTCOLOR', (4, r), (4, r), colors.HexColor('#16a34a')))
        cmd.append(('FONTNAME',  (4, r), (4, r), 'Helvetica-Bold'))

    txn_table.setStyle(TableStyle(cmd))
    story.append(txn_table)
    story.append(Spacer(1, 6 * mm))

    # ── Solde final ────────────────────────────────────────────────
    bal_color = '#16a34a' if bank_account.balance >= 0 else '#dc2626'
    balance_tbl = Table(
        [[Paragraph(
            f'<font name="Helvetica" size="8.5" color="#64748b">'
            f'Solde au {date_to.strftime("%d/%m/%Y")}</font>',
            ParagraphStyle('BL', alignment=TA_RIGHT),
          ),
          Paragraph(
            f'<font name="Helvetica-Bold" size="14" color="{bal_color}">'
            f'{bank_account.balance:,.2f} {bank_account.currency}</font>',
            ParagraphStyle('BV', alignment=TA_RIGHT),
          )]],
        colWidths=[120 * mm, 60 * mm],
    )
    balance_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX',           (0, 0), (-1, -1), 0.8, primary),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING',   (0, 0), (-1, -1), 12),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 12),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(balance_tbl)

    doc.build(story, onFirstPage=page_fn, onLaterPages=page_fn)
    buffer.seek(0)
    return buffer
