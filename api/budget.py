from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum

from .models import Transaction


def _add_month(year, month):
    if month == 12:
        return year + 1, 1
    return year, month + 1


def get_objectif_period_bounds(obj, today=None):
    today = today or date.today()
    if obj.date_debut and obj.date_fin:
        return obj.date_debut, obj.date_fin + timedelta(days=1)

    if obj.periode == 'annuel':
        year = obj.annee or today.year
        start = date(year, 1, 1)
        end = date(year + 1, 1, 1)
        return start, end

    if obj.periode == 'hebdomadaire':
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=7)
        return start, end

    year = obj.annee or today.year
    month = obj.mois or today.month
    start = date(year, month, 1)
    next_year, next_month = _add_month(year, month)
    end = date(next_year, next_month, 1)
    return start, end


def get_objectif_period_key(obj, today=None):
    start, end = get_objectif_period_bounds(obj, today=today)
    return f'{obj.periode}:{start.isoformat()}:{end.isoformat()}'


def get_objectif_progression(obj, entreprise_ids=None, today=None):
    start, end = get_objectif_period_bounds(obj, today=today)
    qs = Transaction.objects.filter(type=obj.type, date__gte=start, date__lt=end)
    if entreprise_ids is not None:
        qs = qs.filter(entreprise_id__in=entreprise_ids)
    if obj.type == 'revenu' and obj.entreprise_id:
        qs = qs.filter(entreprise_id=obj.entreprise_id)
    if obj.type == 'depense' and obj.categorie:
        qs = qs.filter(categorie=obj.categorie)

    total = qs.aggregate(t=Sum('montant'))['t'] or Decimal('0')
    montant = obj.montant or Decimal('0')
    pct = float(total / montant * 100) if montant else 0
    reste = montant - total

    if obj.type == 'depense':
        if total > montant:
            statut = 'depassement'
        elif pct >= obj.seuil_alerte:
            statut = 'proche_limite'
        else:
            statut = 'ok'
    else:
        if total >= montant:
            statut = 'atteint'
        elif pct >= obj.seuil_alerte:
            statut = 'proche_objectif'
        else:
            statut = 'en_cours'

    return {
        'total': float(total),
        'objectif': float(montant),
        'pourcentage': round(pct, 1),
        'seuil_alerte': obj.seuil_alerte,
        'depasse': total > montant,
        'reste': float(reste),
        'statut': statut,
        'periode_debut': start.isoformat(),
        'periode_fin': (end - timedelta(days=1)).isoformat(),
    }
