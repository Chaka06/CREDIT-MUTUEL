COUNTRY_PREFIXES = {
    'France': 'FR',
    'Belgique': 'BE',
    'Italie': 'IT',
    'Espagne': 'ES',
    'Allemagne': 'DE',
    'Portugal': 'PT',
    'Suisse': 'CH',
    'Luxembourg': 'LU',
    'Pays-Bas': 'NL',
    'Royaume-Uni': 'GB',
    'États-Unis': 'US',
    'Canada': 'CA',
    'Maroc': 'MA',
    'Sénégal': 'SN',
    "Côte d'Ivoire": 'CI',
    'Cameroun': 'CM',
    'Algérie': 'DZ',
    'Tunisie': 'TN',
}

COUNTRY_CURRENCIES = {
    'France': 'EUR',
    'Belgique': 'EUR',
    'Italie': 'EUR',
    'Espagne': 'EUR',
    'Allemagne': 'EUR',
    'Portugal': 'EUR',
    'Luxembourg': 'EUR',
    'Pays-Bas': 'EUR',
    'Suisse': 'CHF',
    'Royaume-Uni': 'GBP',
    'États-Unis': 'USD',
    'Canada': 'CAD',
    'Maroc': 'MAD',
    'Sénégal': 'XOF',
    "Côte d'Ivoire": 'XOF',
    'Cameroun': 'XAF',
    'Algérie': 'DZD',
    'Tunisie': 'TND',
}

# Codes bancaires Crédit Mutuel pour la capitale de chaque pays
# code_banque: identifiant de l'établissement (5 chiffres)
# code_guichet: identifiant de l'agence capitale (5 chiffres)
# swift: code BIC/SWIFT de la succursale CM du pays
COUNTRY_BANKING_DATA = {
    'France': {
        'code_banque': '10278',    # CM France — Paris (siège)
        'code_guichet': '06016',   # Agence Paris 8e — Champs-Élysées
        'swift': 'CMCIFRPPXXX',
    },
    'Belgique': {
        'code_banque': '14924',    # CM Belgique — Bruxelles capitale
        'code_guichet': '00001',
        'swift': 'CPHBBEBB',
    },
    'Italie': {
        'code_banque': '03268',    # CM Italie — Rome capitale
        'code_guichet': '01600',
        'swift': 'CMCIITMM',
    },
    'Espagne': {
        'code_banque': '20482',    # CM Espagne — Madrid capitale
        'code_guichet': '00020',
        'swift': 'CMCIESMM',
    },
    'Allemagne': {
        'code_banque': '50040000', # CM Allemagne — Berlin capitale
        'code_guichet': '00000',
        'swift': 'CMCIDEFX',
    },
    'Portugal': {
        'code_banque': '00350',    # CM Portugal — Lisbonne capitale
        'code_guichet': '00001',
        'swift': 'CMCIPTPL',
    },
    'Suisse': {
        'code_banque': '80808',    # CM Suisse — Berne capitale
        'code_guichet': '00001',
        'swift': 'CMCICHZZ',
    },
    'Luxembourg': {
        'code_banque': '00999',    # CM Luxembourg — Luxembourg-Ville
        'code_guichet': '00010',
        'swift': 'CMCILULL',
    },
    'Pays-Bas': {
        'code_banque': '09100',    # CM Pays-Bas — Amsterdam capitale
        'code_guichet': '00001',
        'swift': 'CMCINL2A',
    },
    'Royaume-Uni': {
        'code_banque': '40001',    # CM UK — Londres capitale
        'code_guichet': '00001',
        'swift': 'CMCIGB2L',
    },
    'États-Unis': {
        'code_banque': '02600',    # CM USA — Washington DC capitale
        'code_guichet': '09593',
        'swift': 'CMCIUSNA',
    },
    'Canada': {
        'code_banque': '00600',    # CM Canada — Ottawa capitale
        'code_guichet': '10001',
        'swift': 'CMCICATT',
    },
    'Maroc': {
        'code_banque': '01100',    # CM Maroc — Rabat capitale
        'code_guichet': '02051',
        'swift': 'CMCIMAMC',
    },
    'Sénégal': {
        'code_banque': '09001',    # CM Sénégal — Dakar capitale
        'code_guichet': '00001',
        'swift': 'CMCISNDA',
    },
    "Côte d'Ivoire": {
        'code_banque': '09003',    # CM Côte d'Ivoire — Abidjan (capitale économique)
        'code_guichet': '00001',
        'swift': 'CMCICIAB',
    },
    'Cameroun': {
        'code_banque': '09005',    # CM Cameroun — Yaoundé capitale
        'code_guichet': '00001',
        'swift': 'CMCICMYN',
    },
    'Algérie': {
        'code_banque': '00200',    # CM Algérie — Alger capitale
        'code_guichet': '01000',
        'swift': 'CMCIDZAL',
    },
    'Tunisie': {
        'code_banque': '00700',    # CM Tunisie — Tunis capitale
        'code_guichet': '00001',
        'swift': 'CMCITNTU',
    },
}

COUNTRY_LIST = sorted(COUNTRY_PREFIXES.keys())
