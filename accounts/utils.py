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

logger = logging.getLogger('banking.utils')


# ── Brevo SMTP ────────────────────────────────────────────────────────────

def _send_email(from_name: str, to_email: str, subject: str, html_body: str):
    from django.core.mail import EmailMessage
    msg = EmailMessage(
        subject=subject,
        body=html_body,
        from_email=f"{from_name} <{settings.DEFAULT_FROM_EMAIL}>",
        to=[to_email],
    )
    msg.content_subtype = 'html'
    msg.send()


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

    from django.conf import settings
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


# ── PDF : canvas helpers ───────────────────────────────────────────────────

def _hex_to_rgb(hex_color):
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4))


def _draw_arc_text(canvas, text, cx, cy, radius, angle_start, angle_end,
                   font_name='Helvetica-Bold', font_size=6, top_arc=True):
    """Place each character individually along a circular arc."""
    n = len(text)
    if n == 0:
        return
    span = angle_end - angle_start
    canvas.setFont(font_name, font_size)
    for i, char in enumerate(text):
        t = i / max(n - 1, 1)
        angle_deg = angle_start + t * span
        angle_rad = math.radians(angle_deg)
        x = cx + radius * math.cos(angle_rad)
        y = cy + radius * math.sin(angle_rad)
        rotate = angle_deg - 90 if top_arc else angle_deg + 90
        canvas.saveState()
        canvas.translate(x, y)
        canvas.rotate(rotate)
        canvas.drawCentredString(0, 0, char)
        canvas.restoreState()


def _draw_diamond(canvas, cx, cy, size=1.6):
    """Filled diamond separator."""
    path = canvas.beginPath()
    path.moveTo(cx, cy + size)
    path.lineTo(cx + size, cy)
    path.lineTo(cx, cy - size)
    path.lineTo(cx - size, cy)
    path.close()
    canvas.drawPath(path, fill=1, stroke=0)


def _draw_stamp(canvas, bank, cx, cy, radius=18*mm):
    """
    Cachet officiel Crédit Mutuel — 4 anneaux concentriques, anneau extérieur plein rouge,
    texte arqué, monogramme CM central avec SWIFT et date.
    """
    primary   = _hex_to_rgb(bank.color_primary)
    white_rgb = (1.0, 1.0, 1.0)

    R       = radius          # rayon extérieur total
    R_outer = R               # bord du remplissage rouge
    R_inner = R - 4.5*mm      # bord intérieur de l'anneau rouge → zone blanche
    R_text  = R - 2.3*mm      # axe du texte arqué (au milieu de l'anneau rouge)
    R_mid   = R - 5.2*mm      # premier cercle intérieur (trait)
    R_zone  = R - 6.6*mm      # deuxième cercle (trait) → bord de la zone centrale

    canvas.saveState()

    # ── 1. Anneau rouge extérieur plein ──────────────────────────
    canvas.setFillColorRGB(*primary)
    canvas.setStrokeColorRGB(*primary)
    # Disque rouge complet
    canvas.circle(cx, cy, R_outer, stroke=0, fill=1)
    # Masque blanc intérieur → crée l'anneau rouge
    canvas.setFillColorRGB(*white_rgb)
    canvas.circle(cx, cy, R_inner, stroke=0, fill=1)

    # ── 2. Texte arqué — haut : NOM DE LA BANQUE ─────────────────
    canvas.setFillColorRGB(*white_rgb)
    bank_name_up = bank.name.upper()
    # Calculer la taille de fonte selon la longueur
    name_fs = 6.5 if len(bank_name_up) <= 14 else 5.5
    _draw_arc_text(canvas, bank_name_up, cx, cy, R_text,
                   148, 32, 'Helvetica-Bold', name_fs, top_arc=True)

    # ── 3. Texte arqué — bas : DOCUMENT CERTIFIÉ ─────────────────
    canvas.setFillColorRGB(*white_rgb)
    _draw_arc_text(canvas, 'DOCUMENT  CERTIFIE', cx, cy, R_text,
                   214, 326, 'Helvetica-Bold', 5.2, top_arc=False)

    # ── 4. Séparateurs diamants (à 9° et 171°) ───────────────────
    canvas.setFillColorRGB(*white_rgb)
    diam_r = (R_outer + R_inner) / 2
    for ang in (9, 171):
        a = math.radians(ang)
        _draw_diamond(canvas,
                      cx + diam_r * math.cos(a),
                      cy + diam_r * math.sin(a),
                      size=1.8)

    # ── 5. Cercle de délimitation intérieur (trait rouge) ─────────
    canvas.setStrokeColorRGB(*primary)
    canvas.setFillColorRGB(*primary)
    canvas.setLineWidth(0.8)
    canvas.circle(cx, cy, R_mid, stroke=1, fill=0)

    # ── 6. Deuxième cercle intérieur (trait rouge fin) ────────────
    canvas.setLineWidth(0.5)
    canvas.circle(cx, cy, R_zone, stroke=1, fill=0)

    # ── 7. Monogramme central : CM ou initiales ────────────────────
    # Fond rouge léger dans la zone centrale
    canvas.setFillColorRGB(primary[0], primary[1], primary[2])
    canvas.setFillAlpha(0.06)
    canvas.circle(cx, cy, R_zone - 0.3*mm, stroke=0, fill=1)
    canvas.setFillAlpha(1.0)

    # Grandes initiales CM
    words = bank.name.split()
    if len(words) >= 2:
        initials = words[0][0].upper() + words[1][0].upper()
    else:
        initials = bank.name[:2].upper()

    canvas.setFillColorRGB(*primary)
    canvas.setFont('Helvetica-Bold', 14)
    canvas.drawCentredString(cx, cy + 2.8*mm, initials)

    # Trait horizontal rouge
    rule_w = R_zone * 0.62
    canvas.setLineWidth(0.8)
    canvas.setStrokeColorRGB(*primary)
    canvas.line(cx - rule_w, cy + 1.4*mm, cx + rule_w, cy + 1.4*mm)

    # SWIFT
    swift_text = bank.swift[:11] if bank.swift else 'CMCIFRPPXXX'
    canvas.setFont('Helvetica-Bold', 6)
    canvas.setFillColorRGB(*primary)
    canvas.drawCentredString(cx, cy - 1.2*mm, swift_text)

    # Trait horizontal rouge bas
    canvas.setLineWidth(0.6)
    canvas.line(cx - rule_w, cy - 2.4*mm, cx + rule_w, cy - 2.4*mm)

    # Date
    canvas.setFont('Helvetica', 5.2)
    canvas.setFillColorRGB(0.35, 0.35, 0.35)
    canvas.drawCentredString(cx, cy - 4.5*mm, datetime.now().strftime('%d/%m/%Y'))

    canvas.restoreState()


def _get_logo_reader(bank):
    """Retourne un ImageReader ReportLab pour le logo, via URL Supabase ou chemin local."""
    if not bank.logo:
        return None
    try:
        raw = bank.logo.url
        if raw.startswith('http'):
            resp = _requests.get(raw, timeout=5)
            if resp.status_code == 200:
                return ImageReader(io.BytesIO(resp.content))
    except Exception:
        pass
    try:
        path = bank.logo.path
        if os.path.exists(path):
            return path
    except Exception:
        pass
    return None


def _page_bg(canvas, doc, bank, doc_type):
    """
    Header Crédit Mutuel + footer avec cachet officiel sur chaque page.
    Design : bande rouge CM en haut, ligne décorative, type de document, infos bas de page + cachet.
    """
    PAGE_W, PAGE_H = A4
    ML, MR = 20*mm, 20*mm
    primary  = _hex_to_rgb(bank.color_primary)
    navy     = (0.0,  0.24, 0.49)   # #003d7c
    gray     = (0.42, 0.45, 0.50)
    light_bg = (0.98, 0.98, 0.99)

    canvas.saveState()

    # ── 1. Barre rouge pleine en haut de page ─────────────────────
    RED_BAR_H = 8*mm
    canvas.setFillColorRGB(*primary)
    canvas.rect(0, PAGE_H - RED_BAR_H, PAGE_W, RED_BAR_H, stroke=0, fill=1)

    # ── 2. Fond gris clair de la zone header (sous la barre rouge) ─
    HEADER_H = 34*mm
    canvas.setFillColorRGB(*light_bg)
    canvas.rect(0, PAGE_H - RED_BAR_H - HEADER_H, PAGE_W, HEADER_H, stroke=0, fill=1)

    # ── 3. Logo ou monogramme CM — gauche ─────────────────────────
    logo_y = PAGE_H - RED_BAR_H - HEADER_H / 2
    logo_drawn = False
    logo_img = _get_logo_reader(bank)
    if logo_img:
        try:
            canvas.drawImage(
                logo_img,
                ML, logo_y - 8*mm,
                width=44*mm, height=16*mm,
                preserveAspectRatio=True, anchor='sw', mask='auto'
            )
            logo_drawn = True
        except Exception:
            pass

    if not logo_drawn:
        # Monogramme CM stylisé (boîte rouge + initiales blanches)
        box_x, box_y = ML, logo_y - 6*mm
        box_s = 12*mm
        canvas.setFillColorRGB(*primary)
        canvas.roundRect(box_x, box_y, box_s, box_s, 1.5*mm, stroke=0, fill=1)
        canvas.setFillColorRGB(1, 1, 1)
        canvas.setFont('Helvetica-Bold', 9)
        canvas.drawCentredString(box_x + box_s / 2, box_y + 3.6*mm, 'CM')

        # Nom de la banque
        canvas.setFillColorRGB(*primary)
        canvas.setFont('Helvetica-Bold', 12)
        canvas.drawString(box_x + box_s + 3*mm, logo_y + 0.5*mm, bank.name)
        if bank.tagline:
            canvas.setFillColorRGB(*gray)
            canvas.setFont('Helvetica', 7)
            canvas.drawString(box_x + box_s + 3*mm, logo_y - 4.5*mm, bank.tagline)

    # ── 4. Séparateur vertical + infos banque — droite ────────────
    right_x = PAGE_W - MR
    canvas.setFillColorRGB(*gray)
    canvas.setFont('Helvetica', 7)
    canvas.drawRightString(right_x, logo_y + 3*mm,
                           f"Tél : {bank.phone}" if bank.phone else bank.email)
    canvas.setFont('Helvetica', 6.5)
    canvas.drawRightString(right_x, logo_y - 2*mm,
                           datetime.now().strftime('Le %d %B %Y'))

    # ── 5. Ligne primaire rouge sous le header ─────────────────────
    rule_y = PAGE_H - RED_BAR_H - HEADER_H
    canvas.setStrokeColorRGB(*primary)
    canvas.setLineWidth(2.0)
    canvas.line(0, rule_y, PAGE_W, rule_y)

    # ── 6. Type de document — zone bleue marine centrée ────────────
    doc_bg_h = 11*mm
    doc_bg_y  = rule_y - doc_bg_h
    canvas.setFillColorRGB(*navy)
    canvas.rect(0, doc_bg_y, PAGE_W, doc_bg_h, stroke=0, fill=1)
    canvas.setFillColorRGB(1, 1, 1)
    canvas.setFont('Helvetica-Bold', 10)
    canvas.drawCentredString(PAGE_W / 2, doc_bg_y + 3.4*mm, doc_type)

    # Trait fin blanc en bas du bandeau bleu
    canvas.setStrokeColorRGB(1, 1, 1)
    canvas.setLineWidth(0.3)
    canvas.line(ML, doc_bg_y, PAGE_W - MR, doc_bg_y)

    # ── 7. Footer ─────────────────────────────────────────────────
    FOOTER_Y = 32*mm

    # Fond léger
    canvas.setFillColorRGB(*light_bg)
    canvas.rect(0, 0, PAGE_W, FOOTER_Y + 4*mm, stroke=0, fill=1)

    # Ligne séparatrice rouge
    canvas.setStrokeColorRGB(*primary)
    canvas.setLineWidth(1.0)
    canvas.line(0, FOOTER_Y + 4*mm, PAGE_W, FOOTER_Y + 4*mm)

    # Carré rouge décoratif gauche
    canvas.setFillColorRGB(*primary)
    canvas.rect(0, 0, 5*mm, FOOTER_Y + 4*mm, stroke=0, fill=1)

    # Texte footer
    canvas.setFillColorRGB(*gray)
    canvas.setFont('Helvetica-Bold', 7)
    canvas.drawString(ML, FOOTER_Y, bank.name)

    parts = []
    if bank.address: parts.append(bank.address)
    if bank.phone:   parts.append(f"Tél : {bank.phone}")
    if bank.email:   parts.append(bank.email)
    canvas.setFont('Helvetica', 6.5)
    canvas.drawString(ML, FOOTER_Y - 5*mm, '  ·  '.join(parts)[:90])

    canvas.setFont('Helvetica', 6)
    canvas.setFillColorRGB(0.65, 0.67, 0.70)
    canvas.drawString(ML, FOOTER_Y - 10*mm,
                      "Document officiel généré par le système bancaire Crédit Mutuel — "
                      "Ne constitue pas un contrat sans signature manuscrite.")

    # ── 8. Cachet officiel — bas droit ────────────────────────────
    stamp_cx = PAGE_W - MR - 19*mm
    stamp_cy = (FOOTER_Y + 4*mm) / 2
    _draw_stamp(canvas, bank, stamp_cx, stamp_cy, radius=18*mm)

    canvas.restoreState()


def _build_info_table(data, primary, col_widths=None):
    if col_widths is None:
        col_widths = [65*mm, 105*mm]
    table = Table(data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f8fafc')),
        ('TEXTCOLOR', (0, 0), (0, -1), primary),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9.5),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('LINEBELOW', (0, 0), (-1, -2), 0.3, colors.HexColor('#e5e7eb')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return table


# ── PDF RIB ────────────────────────────────────────────────────────────────

def generate_rib_pdf(bank_account, all_accounts=None):
    buffer = io.BytesIO()
    bank = bank_account.bank
    primary = colors.HexColor(bank.color_primary)

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=58*mm, bottomMargin=42*mm,
        leftMargin=20*mm, rightMargin=20*mm,
    )
    story = []
    page_fn = lambda c, d: _page_bg(c, d, bank, "RELEVÉ D'IDENTITÉ BANCAIRE (RIB)")

    story.append(Spacer(1, 3*mm))

    common_data = [
        ['Titulaire du compte', bank_account.get_full_name()],
        ['Domiciliation', bank.name],
        ['Adresse de la banque', bank.address],
        ['BIC / SWIFT', bank_account.bank_swift or '—'],
        ['Pays', bank_account.country],
        ['Devise', bank_account.currency],
    ]
    story.append(_build_info_table(common_data, primary))
    story.append(Spacer(1, 7*mm))

    accounts_to_show = all_accounts if (all_accounts and len(all_accounts) > 1) else [bank_account]
    for acc in accounts_to_show:
        label = acc.get_account_type_display().upper()
        story.append(Paragraph(
            f'<b>{label}</b>',
            ParagraphStyle('AccLabel', fontSize=9, textColor=primary,
                           fontName='Helvetica-Bold', spaceBefore=4, spaceAfter=3,
                           leftIndent=2)
        ))
        iban_fmt = ' '.join(acc.rib[i:i+4] for i in range(0, len(acc.rib), 4))
        acc_data = [
            ['Code banque',  acc.rib_code_banque],
            ['Code guichet', acc.rib_code_guichet],
            ['N° de compte', acc.rib_numero_compte],
            ['Clé RIB',      acc.rib_cle],
            ['IBAN',         iban_fmt],
        ]
        story.append(_build_info_table(acc_data, primary))
        story.append(Spacer(1, 4*mm))

    story.append(Spacer(1, 4*mm))
    story.append(KeepTogether([
        Paragraph(
            "Je soussigné(e), certifie que les coordonnées bancaires figurant sur ce document "
            f"sont exactes et correspondent à mon/mes compte(s) ouvert(s) auprès de <b>{bank.name}</b>.",
            ParagraphStyle('Decl', fontSize=9, textColor=colors.HexColor('#374151'),
                           leading=14, spaceAfter=12, leftIndent=4, rightIndent=4)
        ),
    ]))

    doc.build(story, onFirstPage=page_fn, onLaterPages=page_fn)
    buffer.seek(0)
    return buffer


# ── PDF Bordereau de virement ──────────────────────────────────────────────

def generate_transfer_slip_pdf(transaction):
    buffer = io.BytesIO()
    bank = transaction.account.bank
    primary = colors.HexColor(bank.color_primary)

    STATUS_CONFIG = {
        'pending':   ('#fef9c3', '#92400e', '#f59e0b', 'EN COURS DE VALIDATION'),
        'validated': ('#f0fdf4', '#166534', '#22c55e', 'VALIDÉ'),
        'rejected':  ('#fef2f2', '#991b1b', '#ef4444', 'REJETÉ'),
    }
    s_bg, s_fg, s_border, s_label = STATUS_CONFIG.get(
        transaction.status, ('#f3f4f6', '#374151', '#9ca3af', transaction.status.upper())
    )

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=58*mm, bottomMargin=42*mm,
        leftMargin=20*mm, rightMargin=20*mm,
    )
    story = []
    page_fn = lambda c, d: _page_bg(c, d, bank, "BORDEREAU DE VIREMENT")

    story.append(Spacer(1, 4*mm))
    status_table = Table(
        [[Paragraph(f'<b>● {s_label}</b>',
                    ParagraphStyle('StatusLabel', fontSize=11, textColor=colors.HexColor(s_fg),
                                   alignment=TA_CENTER, fontName='Helvetica-Bold'))]],
        colWidths=[166*mm],
    )
    status_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(s_bg)),
        ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor(s_border)),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(status_table)
    story.append(Spacer(1, 6*mm))

    data = [
        ['Référence', transaction.reference],
        ['Date d\'initiation', transaction.created_at.strftime('%d/%m/%Y à %H:%M')],
        ['Type', transaction.get_transaction_type_display()],
        ['Montant', f"{transaction.amount:,.2f} {transaction.currency}"],
        ["Donneur d'ordre", transaction.account.get_full_name()],
        ["IBAN donneur d'ordre", transaction.account.rib],
        ['Bénéficiaire', transaction.get_beneficiary_display_name()],
        ['IBAN bénéficiaire', (transaction.beneficiary.account_number if transaction.beneficiary else transaction.beneficiary_iban) or '—'],
        ['Banque bénéficiaire', (transaction.beneficiary.bank_name if transaction.beneficiary else transaction.beneficiary_bank) or '—'],
        ['Motif / Libellé', transaction.description or '—'],
    ]

    if transaction.status == 'validated' and transaction.validated_at:
        data.append(['Date de validation', transaction.validated_at.strftime('%d/%m/%Y à %H:%M')])

    if transaction.status == 'rejected':
        if transaction.validated_at:
            data.append(['Date de rejet', transaction.validated_at.strftime('%d/%m/%Y à %H:%M')])
        data.append(['Motif du rejet', transaction.rejection_reason or '—'])
        if transaction.rejection_fee:
            data.append(['Frais de redirection', f"{transaction.rejection_fee:,.2f} {transaction.currency}"])
            data.append(['Note', 'Les frais sont à régler en agence — non déductibles en ligne.'])

    story.append(_build_info_table(data, primary))
    doc.build(story, onFirstPage=page_fn, onLaterPages=page_fn)
    buffer.seek(0)
    return buffer


# ── PDF Relevé de compte ───────────────────────────────────────────────────

def generate_statement_pdf(bank_account, transactions, date_from, date_to):
    buffer = io.BytesIO()
    bank = bank_account.bank
    primary = colors.HexColor(bank.color_primary)

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=58*mm, bottomMargin=42*mm,
        leftMargin=15*mm, rightMargin=15*mm,
    )
    story = []
    period = f"Période du {date_from.strftime('%d/%m/%Y')} au {date_to.strftime('%d/%m/%Y')}"
    page_fn = lambda c, d: _page_bg(c, d, bank, f"RELEVÉ DE COMPTE  —  {period}")

    story.append(Spacer(1, 3*mm))

    account_info = Table(
        [['Titulaire', bank_account.get_full_name()],
         ['IBAN', bank_account.rib],
         ['Devise', bank_account.currency]],
        colWidths=[45*mm, 135*mm]
    )
    account_info.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (0, -1), primary),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f8fafc')),
        ('LINEBELOW', (0, 0), (-1, -2), 0.3, colors.HexColor('#e5e7eb')),
        ('BOX', (0, 0), (-1, -1), 0.4, colors.HexColor('#e5e7eb')),
    ]))
    story.append(account_info)
    story.append(Spacer(1, 5*mm))

    headers = ['Date', 'Référence', 'Libellé', 'Débit', 'Crédit', 'Statut']
    rows = [headers]
    total_debit = 0
    total_credit = 0

    for txn in transactions:
        if txn.is_debit:
            debit = f"{txn.amount:,.2f}"
            credit = ''
            total_debit += float(txn.amount)
        else:
            debit = ''
            credit = f"{txn.amount:,.2f}"
            total_credit += float(txn.amount)

        rows.append([
            txn.created_at.strftime('%d/%m/%Y'),
            txn.reference,
            (txn.description or txn.get_transaction_type_display())[:35],
            debit,
            credit,
            txn.get_status_display(),
        ])

    rows.append(['', '', 'TOTAUX', f"{total_debit:,.2f}", f"{total_credit:,.2f}", ''])

    col_widths = [22*mm, 30*mm, 68*mm, 22*mm, 22*mm, 16*mm]
    txn_table = Table(rows, colWidths=col_widths, repeatRows=1)

    debit_rows = [i + 1 for i, r in enumerate(rows[1:]) if r[3]]
    credit_rows = [i + 1 for i, r in enumerate(rows[1:]) if r[4]]

    style_commands = [
        ('BACKGROUND', (0, 0), (-1, 0), primary),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f9fafb')]),
        ('GRID', (0, 0), (-1, -1), 0.2, colors.HexColor('#e5e7eb')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('ALIGN', (3, 0), (4, -1), 'RIGHT'),
        ('BACKGROUND', (0, len(rows)-1), (-1, len(rows)-1), colors.HexColor('#f1f5f9')),
        ('FONTNAME', (0, len(rows)-1), (-1, len(rows)-1), 'Helvetica-Bold'),
    ]
    for r in debit_rows:
        style_commands.append(('TEXTCOLOR', (3, r), (3, r), colors.HexColor('#dc2626')))
    for r in credit_rows:
        style_commands.append(('TEXTCOLOR', (4, r), (4, r), colors.HexColor('#16a34a')))

    txn_table.setStyle(TableStyle(style_commands))
    story.append(txn_table)
    story.append(Spacer(1, 5*mm))

    story.append(Paragraph(
        f"Solde au {date_to.strftime('%d/%m/%Y')} : <b>{bank_account.balance:,.2f} {bank_account.currency}</b>",
        ParagraphStyle('Balance', fontSize=11, textColor=primary, alignment=TA_RIGHT, spaceAfter=4)
    ))

    doc.build(story, onFirstPage=page_fn, onLaterPages=page_fn)
    buffer.seek(0)
    return buffer
