"""
DeliverPro — Filtres django-filter
"""
import django_filters
from .models import Commande, Transaction


class CommandeFilter(django_filters.FilterSet):
    date_debut = django_filters.DateFilter(field_name='date', lookup_expr='gte', label='Date début')
    date_fin   = django_filters.DateFilter(field_name='date', lookup_expr='lte', label='Date fin')
    prix_min   = django_filters.NumberFilter(field_name='prix', lookup_expr='gte')
    prix_max   = django_filters.NumberFilter(field_name='prix', lookup_expr='lte')

    class Meta:
        model  = Commande
        fields = ['statut', 'entreprise', 'livreur', 'date_debut', 'date_fin', 'prix_min', 'prix_max']


class TransactionFilter(django_filters.FilterSet):
    date_debut = django_filters.DateFilter(field_name='date', lookup_expr='gte')
    date_fin   = django_filters.DateFilter(field_name='date', lookup_expr='lte')
    montant_min = django_filters.NumberFilter(field_name='montant', lookup_expr='gte')
    montant_max = django_filters.NumberFilter(field_name='montant', lookup_expr='lte')

    class Meta:
        model  = Transaction
        fields = ['type', 'entreprise', 'user', 'date_debut', 'date_fin']
