"""
DeliverPro — Filtres django-filter
"""
import django_filters
from .models import Transaction


class TransactionFilter(django_filters.FilterSet):
    date_debut = django_filters.DateFilter(field_name='date', lookup_expr='gte')
    date_fin   = django_filters.DateFilter(field_name='date', lookup_expr='lte')
    montant_min = django_filters.NumberFilter(field_name='montant', lookup_expr='gte')
    montant_max = django_filters.NumberFilter(field_name='montant', lookup_expr='lte')

    class Meta:
        model  = Transaction
        fields = ['type', 'entreprise', 'user', 'date_debut', 'date_fin']
