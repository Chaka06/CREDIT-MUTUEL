"""
Middleware anti brute-force : bloque une IP après N tentatives échouées en M minutes.
"""
from django.utils import timezone
from django.http import HttpResponseForbidden
from datetime import timedelta


MAX_ATTEMPTS_IP      = 10
MAX_ATTEMPTS_ACCOUNT = 5
WINDOW_MINUTES       = 15


def get_client_ip(request):
    # Sur Vercel, x-real-ip contient l'IP client fiable
    real_ip = request.META.get('HTTP_X_REAL_IP')
    if real_ip:
        return real_ip.strip()
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        # Dernier IP = plus proche du proxy Vercel (résistant au spoofing header)
        return x_forwarded.split(',')[-1].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


def is_ip_locked(ip: str) -> bool:
    from accounts.models import LoginAttempt
    window_start = timezone.now() - timedelta(minutes=WINDOW_MINUTES)
    count = LoginAttempt.objects.filter(
        ip_address=ip,
        success=False,
        created_at__gte=window_start,
    ).count()
    return count >= MAX_ATTEMPTS_IP


def is_account_locked(account_id: str) -> bool:
    from accounts.models import LoginAttempt
    window_start = timezone.now() - timedelta(minutes=WINDOW_MINUTES)
    count = LoginAttempt.objects.filter(
        account_id=account_id,
        success=False,
        created_at__gte=window_start,
    ).count()
    return count >= MAX_ATTEMPTS_ACCOUNT


def record_attempt(account_id: str, ip: str, bank_slug: str, success: bool):
    from accounts.models import LoginAttempt
    LoginAttempt.objects.create(
        account_id=account_id,
        ip_address=ip,
        bank_slug=bank_slug,
        success=success,
    )
