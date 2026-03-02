"""
DeliverPro — Routage API
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LoginView, LogoutView, MeView, ChangePasswordView,
    UserViewSet, EntrepriseViewSet, CommandeViewSet,
    TransactionViewSet, ObjectifViewSet,
    DashboardView, DashboardLivreurView,
    BudgetAlertView, ExportPDFView, AuditLogViewSet,
)

router = DefaultRouter()
router.register(r'users',        UserViewSet,        basename='user')
router.register(r'entreprises',  EntrepriseViewSet,  basename='entreprise')
router.register(r'commandes',    CommandeViewSet,    basename='commande')
router.register(r'transactions', TransactionViewSet, basename='transaction')
router.register(r'objectifs',    ObjectifViewSet,    basename='objectif')
router.register(r'audit-logs',   AuditLogViewSet,    basename='auditlog')

urlpatterns = [
    # Auth
    path('auth/login/',           LoginView.as_view(),          name='login'),
    path('auth/logout/',          LogoutView.as_view(),         name='logout'),
    path('auth/me/',              MeView.as_view(),             name='me'),
    path('auth/change-password/', ChangePasswordView.as_view(), name='change-password'),

    # Dashboards
    path('dashboard/',         DashboardView.as_view(),        name='dashboard'),
    path('dashboard/livreur/', DashboardLivreurView.as_view(), name='dashboard-livreur'),
    path('budget/alerts/',     BudgetAlertView.as_view(),      name='budget-alerts'),

    # Export
    path('export/pdf/', ExportPDFView.as_view(), name='export-pdf'),

    # Router (CRUD)
    path('', include(router.urls)),
]
