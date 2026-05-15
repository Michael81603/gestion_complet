"""
DeliverPro — Permissions personnalisées
"""
from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """Seuls les admins peuvent accéder."""
    message = "Accès réservé aux administrateurs."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'admin')


class IsOwnerOrAdmin(BasePermission):
    """L'objet appartient à l'utilisateur ou l'utilisateur est admin."""
    def has_object_permission(self, request, view, obj):
        if request.user.role == 'admin':
            return True
        return False
