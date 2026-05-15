"""
DeliverPro — Interface Admin Django
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Entreprise, EntrepriseAccess, Transaction, Objectif, AuditLog


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display  = ['nom', 'email', 'role', 'actif', 'created_at']
    list_filter   = ['role', 'actif']
    search_fields = ['nom', 'email']
    ordering      = ['-created_at']
    fieldsets = (
        (None,          {'fields': ('email', 'password')}),
        ('Infos',       {'fields': ('nom', 'telephone', 'role', 'actif')}),
        ('Permissions', {'fields': ('is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'nom', 'password1', 'password2'),
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


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display  = ['id', 'type', 'categorie', 'montant', 'label', 'entreprise', 'date']
    list_filter   = ['type', 'categorie', 'entreprise', 'date']
    search_fields = ['label', 'description']
    date_hierarchy = 'date'
    fieldsets = (
        ('Transaction', {'fields': ('type', 'categorie', 'montant', 'label', 'description')}),
        ('Lien', {'fields': ('entreprise', 'user')}),
        ('Date', {'fields': ('date',)}),
    )


@admin.register(Objectif)
class ObjectifAdmin(admin.ModelAdmin):
    list_display = ['label', 'type', 'entreprise', 'categorie', 'montant', 'periode', 'date_debut', 'date_fin', 'mois', 'annee']
    list_filter = ['type', 'entreprise', 'categorie', 'periode']


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
