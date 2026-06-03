from django.shortcuts import render
from django.http import HttpResponse


def landing_view(request):
    """Page d'accueil publique Crédit Mutuel."""
    from banks.models import Bank
    bank = Bank.objects.filter(is_active=True).first()
    return render(request, 'landing.html', {'bank': bank})
