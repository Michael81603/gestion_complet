"""
DeliverPro — Interface Admin Django
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Entreprise, EntrepriseAccess, Commande, Transaction, Objectif, AuditLog


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display  = ['nom', 'email', 'role', 'actif', 'last_location_at', 'created_at']
    list_filter   = ['role', 'actif']
    search_fields = ['nom', 'email']
    ordering      = ['-created_at']
    fieldsets = (
        (None,          {'fields': ('email', 'password')}),
        ('Infos',       {'fields': ('nom', 'telephone', 'role', 'actif')}),
        ('Localisation', {'fields': ('last_latitude', 'last_longitude', 'last_location_at')}),
        ('Permissions', {'fields': ('is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'nom', 'password1', 'password2', 'role'),
        }),
    )


@admin.register(Entreprise)
class EntrepriseAdmin(admin.ModelAdmin):
    list_display  = ['nom', 'adresse', 'telephone', 'date_creation']
    search_fields = ['nom']


@admin.register(EntrepriseAccess)
class EntrepriseAccessAdmin(admin.ModelAdmin):
    list_display = ['user', 'entreprise', 'created_at']
    search_fields = ['user__nom', 'user__email', 'entreprise__nom']


@admin.register(Commande)
class CommandeAdmin(admin.ModelAdmin):
    list_display   = ['id', 'client_nom', 'entreprise', 'livreur', 'prix', 'statut', 'date']
    list_filter    = ['statut', 'entreprise']
    search_fields  = ['client_nom', 'adresse']
    date_hierarchy = 'date'
    raw_id_fields  = ['entreprise', 'livreur']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display  = ['id', 'type', 'montant', 'label', 'entreprise', 'date']
    list_filter   = ['type', 'entreprise']
    search_fields = ['label']
    date_hierarchy = 'date'


@admin.register(Objectif)
class ObjectifAdmin(admin.ModelAdmin):
    list_display = ['label', 'type', 'montant', 'periode', 'mois', 'annee']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display  = ['user', 'action', 'table_name', 'record_id', 'created_at']
    list_filter   = ['action']
    readonly_fields = ['user', 'action', 'table_name', 'record_id', 'details', 'ip_address', 'created_at']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
