"""
DeliverPro — Vues API (ViewSets + APIViews)
"""
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum, Count, Q, ProtectedError
from django.core.cache import cache
from django.core.mail import send_mail
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .budget import get_objectif_period_key, get_objectif_progression
from .models import User, Entreprise, EntrepriseAccess, Transaction, Objectif, AuditLog, BudgetNotification
from .permissions import IsAdmin
from .serializers import (
    LoginSerializer, UserSerializer, UserCreateSerializer, UserUpdateSerializer,
    ChangePasswordSerializer, EntrepriseSerializer, EntrepriseListSerializer,
    TransactionSerializer, TransactionCreateSerializer,
    ObjectifSerializer, AuditLogSerializer,
)
from .utils import log_action, generate_pdf_report
from .realtime import broadcast_event


DASHBOARD_CACHE_TTL = 60
DASHBOARD_CACHE_VERSION_KEY = 'dashboard_cache_version'


def get_dashboard_cache_version():
    return cache.get(DASHBOARD_CACHE_VERSION_KEY, 1)


def invalidate_dashboard_cache():
    """Invalidate dashboard cache without flushing unrelated cache entries."""
    current_version = get_dashboard_cache_version()
    cache.set(DASHBOARD_CACHE_VERSION_KEY, current_version + 1, timeout=None)


def is_global_admin(user):
    """
    Global admins are never constrained by EntrepriseAccess rows.
    Staff/superusers keep full visibility by default.
    """
    return bool(user and user.is_authenticated and user.role == 'admin' and (user.is_staff or user.is_superuser))


def get_admin_scope_ids(user):
    """Renvoie les entreprises accessibles; None = accès global, [] = aucun accès."""
    if not user.is_authenticated or user.role != 'admin':
        return []
    if is_global_admin(user):
        return None
    return list(
        EntrepriseAccess.objects.filter(user=user).values_list('entreprise_id', flat=True)
    )


def apply_admin_scope(qs, user, field='entreprise_id'):
    scope_ids = get_admin_scope_ids(user)
    if scope_ids is None:
        return qs
    if not scope_ids:
        return qs.none()
    return qs.filter(**{f'{field}__in': scope_ids})


def get_period_start(periode, today):
    if periode == 'jour':
        return today
    if periode == 'semaine':
        return today - timedelta(days=7)
    if periode == 'annee':
        return today.replace(month=1, day=1)
    return today.replace(day=1)


def compute_budget_alerts(user, seuil=80):
    objectifs = Objectif.objects.all()
    alerts = []
    for obj in objectifs:
        progression = get_objectif_progression(obj, entreprise_ids=get_admin_scope_ids(user))
        pct = progression['pourcentage']
        objectif_seuil = obj.seuil_alerte or seuil
        if obj.type == 'depense' and progression['statut'] == 'depassement':
            alerts.append({
                'objectif_id': obj.id,
                'label': obj.label or obj.type,
                'categorie': obj.categorie or '',
                'niveau': 'depassement',
                'pourcentage': pct,
                'total': progression['total'],
                'objectif': progression['objectif'],
                'periode_debut': progression['periode_debut'],
                'periode_fin': progression['periode_fin'],
            })
        elif pct >= objectif_seuil:
            alerts.append({
                'objectif_id': obj.id,
                'label': obj.label or obj.type,
                'categorie': obj.categorie or '',
                'niveau': 'proche_limite' if obj.type == 'depense' else 'proche_objectif',
                'pourcentage': pct,
                'total': progression['total'],
                'objectif': progression['objectif'],
                'periode_debut': progression['periode_debut'],
                'periode_fin': progression['periode_fin'],
            })
    return alerts


def _budget_recipients_for_transaction(txn):
    admins = User.objects.filter(role='admin', actif=True, is_active=True).exclude(email='')
    for admin in admins:
        scope_ids = get_admin_scope_ids(admin)
        if scope_ids is None or txn.entreprise_id in scope_ids:
            yield admin, scope_ids


def notify_budget_exceeded(txn):
    if txn.type != 'depense':
        return

    objectifs = Objectif.objects.filter(type='depense', notification_email=True)
    for admin, scope_ids in _budget_recipients_for_transaction(txn):
        for obj in objectifs:
            if obj.categorie and obj.categorie != txn.categorie:
                continue
            progression = get_objectif_progression(obj, entreprise_ids=scope_ids)
            if progression['statut'] != 'depassement':
                continue

            periode_cle = get_objectif_period_key(obj)
            already_sent = BudgetNotification.objects.filter(
                user=admin,
                objectif=obj,
                niveau='depassement',
                periode_cle=periode_cle,
            ).exists()
            if already_sent:
                continue

            subject = f"Alerte budget depasse - {obj.label or 'Budget depenses'}"
            message = (
                f"Bonjour {admin.nom},\n\n"
                f"Le budget \"{obj.label or obj.type}\" est depasse.\n"
                f"Budget prevu : {progression['objectif']:.2f} MGA\n"
                f"Depenses actuelles : {progression['total']:.2f} MGA\n"
                f"Periode : {progression['periode_debut']} au {progression['periode_fin']}\n"
                f"Derniere depense : {txn.label} ({txn.montant} MGA)\n\n"
                "Connectez-vous au dashboard DeliverPro Finance pour verifier les details."
            )

            try:
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [admin.email],
                    fail_silently=False,
                )
                BudgetNotification.objects.create(
                    user=admin,
                    objectif=obj,
                    niveau='depassement',
                    periode_cle=periode_cle,
                    email_to=admin.email,
                    total=Decimal(str(progression['total'])),
                    montant_objectif=Decimal(str(progression['objectif'])),
                )
                log_action(admin, 'BUDGET_EMAIL_SENT', 'objectif', obj.id, {'email': admin.email})
            except Exception as exc:
                log_action(admin, 'BUDGET_EMAIL_FAILED', 'objectif', obj.id, {'error': str(exc), 'email': admin.email})


# ─────────────────────────────────────────────────────────────────────────────
# AUTH VIEWS
# ─────────────────────────────────────────────────────────────────────────────

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']

        refresh = RefreshToken.for_user(user)
        log_action(user, 'LOGIN', ip=request.META.get('REMOTE_ADDR'))

        return Response({
            'access':  str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
        })


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            token = RefreshToken(request.data.get('refresh'))
            token.blacklist()
            log_action(request.user, 'LOGOUT', ip=request.META.get('REMOTE_ADDR'))
        except Exception:
            pass
        return Response({'detail': 'Déconnexion réussie.'})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserUpdateSerializer(
            request.user, data=request.data, partial=True, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save()
        log_action(request.user, 'CHANGE_PASSWORD')
        return Response({'detail': 'Mot de passe modifié avec succès.'})


# ─────────────────────────────────────────────────────────────────────────────
# USER (ADMIN)
# ─────────────────────────────────────────────────────────────────────────────

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    permission_classes = [IsAuthenticated, IsAdmin]
    filterset_fields = ['role', 'actif']
    search_fields = ['nom', 'email']

    def get_queryset(self):
        # Company scoping remains enforced on business datasets.
        return super().get_queryset()

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        if self.action in ('update', 'partial_update'):
            return UserUpdateSerializer
        return UserSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        invalidate_dashboard_cache()
        log_action(self.request.user, 'CREATE_USER', 'user', user.id, {'nom': user.nom})
        broadcast_event(
            'user.created',
            {'id': user.id, 'nom': user.nom, 'role': user.role}
        )

    @action(detail=True, methods=['post'])
    def toggle_actif(self, request, pk=None):
        user = self.get_object()
        user.actif = not user.actif
        user.save()
        invalidate_dashboard_cache()
        log_action(request.user, 'TOGGLE_ACTIF', 'user', user.id)
        broadcast_event(
            'user.updated',
            {'id': user.id, 'actif': user.actif, 'role': user.role}
        )
        return Response({'actif': user.actif})

    @action(detail=False, methods=['post'])
    def change_password(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        log_action(request.user, 'CHANGE_PASSWORD', 'user', user.id)
        return Response({'message': 'Mot de passe changé avec succès.'})


# ─────────────────────────────────────────────────────────────────────────────



# ─────────────────────────────────────────────────────────────────────────────
# ENTREPRISE
# ─────────────────────────────────────────────────────────────────────────────

class EntrepriseViewSet(viewsets.ModelViewSet):
    queryset = Entreprise.objects.all()
    permission_classes = [IsAuthenticated, IsAdmin]
    search_fields = ['nom', 'adresse']

    def get_queryset(self):
        return apply_admin_scope(super().get_queryset(), self.request.user, field='id')

    def get_serializer_class(self):
        if self.action == 'list':
            return EntrepriseListSerializer
        return EntrepriseSerializer

    def perform_create(self, serializer):
        ent = serializer.save()
        # Keep global admins global. Only scoped admins auto-gain access on newly created companies.
        if get_admin_scope_ids(self.request.user) is not None:
            EntrepriseAccess.objects.get_or_create(user=self.request.user, entreprise=ent)
        invalidate_dashboard_cache()
        log_action(self.request.user, 'CREATE_ENTREPRISE', 'entreprise', ent.id, {'nom': ent.nom})
        broadcast_event(
            'entreprise.created',
            {'id': ent.id, 'nom': ent.nom},
            entreprise_id=ent.id,
        )

    def perform_destroy(self, instance):
        ent_id = instance.id
        ent_nom = instance.nom
        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError({
                'detail': "Impossible de supprimer cette entreprise car elle contient des transactions financieres."
            })
        invalidate_dashboard_cache()
        log_action(self.request.user, 'DELETE_ENTREPRISE', 'entreprise', ent_id, {'nom': ent_nom})
        broadcast_event(
            'entreprise.deleted',
            {'id': ent_id},
        )

    @action(detail=True, methods=['get'])
    def dashboard(self, request, pk=None):
        ent = self.get_object()
        periode = request.query_params.get('periode', 'mois')
        today = date.today()
        date_debut = get_period_start(periode, today)
        cache_version = get_dashboard_cache_version()
        cache_key = f"ent_dash:v{cache_version}:{request.user.id}:{ent.id}:{periode}"
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        stats = ent.get_stats()
        txns_qs = Transaction.objects.filter(entreprise=ent)
        if date_debut:
            txns_qs = txns_qs.filter(date__gte=date_debut)

        rev_par_jour = (
            txns_qs.filter(type='revenu')
            .values('date')
            .annotate(total=Sum('montant'))
            .order_by('date')
        )
        dep_par_jour = (
            txns_qs.filter(type='depense')
            .values('date')
            .annotate(total=Sum('montant'))
            .order_by('date')
        )
        rev_par_categorie = list(
            txns_qs.filter(type='revenu').values('categorie').annotate(total=Sum('montant')).order_by('categorie')
        )
        dep_par_categorie = list(
            txns_qs.filter(type='depense').values('categorie').annotate(total=Sum('montant')).order_by('categorie')
        )
        total_revenus = txns_qs.filter(type='revenu').aggregate(t=Sum('montant'))['t'] or Decimal('0')
        total_depenses = txns_qs.filter(type='depense').aggregate(t=Sum('montant'))['t'] or Decimal('0')
        payload = {
            'periode': periode,
            'entreprise': EntrepriseSerializer(ent).data,
            'stats': stats,
            'totaux_periode': {
                'revenus': total_revenus,
                'depenses': total_depenses,
                'benefice': total_revenus - total_depenses,
            },
            'revenus_par_jour': [{'date': str(r['date']), 'total': float(r['total'])} for r in rev_par_jour],
            'depenses_par_jour': [{'date': str(d['date']), 'total': float(d['total'])} for d in dep_par_jour],
            'revenus_par_categorie': rev_par_categorie,
            'depenses_par_categorie': dep_par_categorie,
            'transactions_recentes': TransactionSerializer(
                txns_qs.order_by('-date', '-created_at')[:10],
                many=True,
            ).data,
            'alerts_budget': compute_budget_alerts(request.user),
        }
        cache.set(cache_key, payload, DASHBOARD_CACHE_TTL)
        return Response(payload)



# ─────────────────────────────────────────────────────────────────────────────
# TRANSACTION
# ─────────────────────────────────────────────────────────────────────────────

class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.select_related('entreprise', 'user').all()
    permission_classes = [IsAuthenticated, IsAdmin]
    filterset_fields = ['type', 'categorie', 'entreprise']
    search_fields = ['label', 'description']
    ordering_fields = ['date', 'montant']

    def get_serializer_class(self):
        if self.action == 'create':
            return TransactionCreateSerializer
        return TransactionSerializer

    def _ensure_entreprise_in_scope(self, entreprise_id):
        scope_ids = get_admin_scope_ids(self.request.user)
        if scope_ids is None:
            return
        try:
            ent_id = int(entreprise_id)
        except (TypeError, ValueError):
            raise PermissionDenied("Entreprise invalide.")
        if ent_id not in scope_ids:
            raise PermissionDenied("Entreprise hors périmètre autorisé.")

    def get_queryset(self):
        qs = super().get_queryset()
        qs = apply_admin_scope(qs, self.request.user)
        date_debut = self.request.query_params.get('date_debut')
        date_fin   = self.request.query_params.get('date_fin')
        if date_debut:
            qs = qs.filter(date__gte=date_debut)
        if date_fin:
            qs = qs.filter(date__lte=date_fin)
        return qs

    def perform_create(self, serializer):
        self._ensure_entreprise_in_scope(serializer.validated_data.get('entreprise').id)
        txn = serializer.save(user=serializer.validated_data.get('user') or self.request.user)
        invalidate_dashboard_cache()
        log_action(self.request.user, 'CREATE_TRANSACTION', 'transaction', txn.id)
        broadcast_event(
            'transaction.created',
            {
                'id': txn.id,
                'type': txn.type,
                'montant': float(txn.montant),
                'entreprise_id': txn.entreprise_id,
            },
            entreprise_id=txn.entreprise_id,
        )
        notify_budget_exceeded(txn)

    def _create_manual_transaction(self, request, tx_type):
        payload = request.data.copy()
        payload['type'] = tx_type
        scope_ids = get_admin_scope_ids(request.user)
        ent_id = payload.get('entreprise')
        if scope_ids is not None:
            try:
                ent_id = int(ent_id)
            except (TypeError, ValueError):
                return Response({'error': 'Entreprise invalide.'}, status=400)
            if ent_id not in scope_ids:
                return Response({'error': "Entreprise hors périmètre autorisé."}, status=403)
        serializer = TransactionCreateSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        txn = serializer.save(user=serializer.validated_data.get('user') or request.user)
        invalidate_dashboard_cache()
        log_action(
            request.user,
            'CREATE_TRANSACTION',
            'transaction',
            txn.id,
            {'type': tx_type, 'montant': str(txn.montant)}
        )
        broadcast_event(
            'transaction.created',
            {
                'id': txn.id,
                'type': txn.type,
                'montant': float(txn.montant),
                'entreprise_id': txn.entreprise_id,
            },
            entreprise_id=txn.entreprise_id,
        )
        notify_budget_exceeded(txn)
        return Response(TransactionSerializer(txn).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='ajouter-revenu')
    def ajouter_revenu(self, request):
        return self._create_manual_transaction(request, 'revenu')

    @action(detail=False, methods=['post'], url_path='ajouter-depense')
    def ajouter_depense(self, request):
        return self._create_manual_transaction(request, 'depense')

# ─────────────────────────────────────────────────────────────────────────────
# OBJECTIF
# ─────────────────────────────────────────────────────────────────────────────

class ObjectifViewSet(viewsets.ModelViewSet):
    queryset = Objectif.objects.all()
    serializer_class = ObjectifSerializer
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['entreprise_ids'] = get_admin_scope_ids(self.request.user)
        return ctx

    def perform_create(self, serializer):
        obj = serializer.save()
        invalidate_dashboard_cache()
        log_action(self.request.user, 'CREATE_OBJECTIF', 'objectif', obj.id)
        broadcast_event('objectif.created', {'id': obj.id, 'type': obj.type, 'montant': float(obj.montant)})

    def perform_update(self, serializer):
        obj = serializer.save()
        invalidate_dashboard_cache()
        log_action(self.request.user, 'UPDATE_OBJECTIF', 'objectif', obj.id)
        broadcast_event('objectif.updated', {'id': obj.id, 'type': obj.type, 'montant': float(obj.montant)})

    def perform_destroy(self, instance):
        obj_id = instance.id
        log_action(self.request.user, 'DELETE_OBJECTIF', 'objectif', obj_id)
        instance.delete()
        invalidate_dashboard_cache()
        broadcast_event('objectif.deleted', {'id': obj_id})


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD GLOBAL
# ─────────────────────────────────────────────────────────────────────────────

class DashboardView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        periode = request.query_params.get('periode', 'mois')  # jour, semaine, mois, annee
        scope_ids = get_admin_scope_ids(request.user)
        scope_part = 'global' if scope_ids is None else ','.join(str(i) for i in sorted(scope_ids)) or 'none'
        cache_version = get_dashboard_cache_version()
        cache_key = f"global_dash:v{cache_version}:{request.user.id}:{periode}:{scope_part}"
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        today = date.today()
        date_debut = get_period_start(periode, today)

        txns = apply_admin_scope(Transaction.objects.filter(date__gte=date_debut), request.user)
        revenus  = txns.filter(type='revenu').aggregate(t=Sum('montant'))['t'] or Decimal('0')
        depenses = txns.filter(type='depense').aggregate(t=Sum('montant'))['t'] or Decimal('0')
        benefice = revenus - depenses
        nb_revenus = txns.filter(type='revenu').count()
        nb_depenses = txns.filter(type='depense').count()
        nb_transactions = nb_revenus + nb_depenses
        marge_nette = (benefice / revenus * 100) if revenus else Decimal('0')
        revenu_moyen = (revenus / nb_revenus) if nb_revenus else Decimal('0')
        depense_moyenne = (depenses / nb_depenses) if nb_depenses else Decimal('0')

        # Revenu par jour (30 derniers jours)
        rev_par_jour = (
            apply_admin_scope(
                Transaction.objects.filter(type='revenu', date__gte=today - timedelta(days=30)),
                request.user,
            )
            .values('date')
            .annotate(total=Sum('montant'))
            .order_by('date')
        )
        dep_par_jour = (
            apply_admin_scope(
                Transaction.objects.filter(type='depense', date__gte=today - timedelta(days=30)),
                request.user,
            )
            .values('date')
            .annotate(total=Sum('montant'))
            .order_by('date')
        )

        revenus_par_categorie = list(
            txns.filter(type='revenu')
            .values('categorie')
            .annotate(total=Sum('montant'), count=Count('id'))
            .order_by('-total')
        )
        depenses_par_categorie = list(
            txns.filter(type='depense')
            .values('categorie')
            .annotate(total=Sum('montant'), count=Count('id'))
            .order_by('-total')
        )

        transactions_par_entreprise = list(
            txns.values('entreprise__id', 'entreprise__nom')
            .annotate(
                revenus=Sum('montant', filter=Q(type='revenu')),
                depenses=Sum('montant', filter=Q(type='depense')),
                total=Count('id'),
            )
            .order_by('-revenus', 'entreprise__nom')
        )

        entreprises_qs = apply_admin_scope(Entreprise.objects.all(), request.user, field='id')
        entreprises_stats = []
        for ent in entreprises_qs:
            ent_txns = txns.filter(entreprise=ent)
            ent_revenus = ent_txns.filter(type='revenu').aggregate(t=Sum('montant'))['t'] or Decimal('0')
            ent_depenses = ent_txns.filter(type='depense').aggregate(t=Sum('montant'))['t'] or Decimal('0')
            entreprises_stats.append({
                'id': ent.id, 'nom': ent.nom,
                'revenus': ent_revenus,
                'depenses': ent_depenses,
                'benefice': ent_revenus - ent_depenses,
                'nb_transactions': ent_txns.count(),
            })

        transactions_recentes = apply_admin_scope(
            Transaction.objects.select_related('entreprise', 'user').all(),
            request.user,
        ).order_by('-date', '-created_at')[:8]
        objectifs = ObjectifSerializer(
            Objectif.objects.all(),
            many=True,
            context={'entreprise_ids': scope_ids},
        ).data
        payload = {
            'periode':         periode,
            'revenus_total':   revenus,
            'depenses_total':  depenses,
            'benefice_net':    benefice,
            'marge_nette_percent': round(float(marge_nette), 2),
            'revenu_moyen': revenu_moyen,
            'depense_moyenne': depense_moyenne,
            'nb_transactions': nb_transactions,
            'nb_revenus': nb_revenus,
            'nb_depenses': nb_depenses,
            'revenus_par_jour': [
                {'date': str(r['date']), 'total': float(r['total'])} for r in rev_par_jour
            ],
            'depenses_par_jour': [
                {'date': str(d['date']), 'total': float(d['total'])} for d in dep_par_jour
            ],
            'entreprises_stats': entreprises_stats,
            'transactions_par_entreprise': transactions_par_entreprise,
            'revenus_par_categorie': revenus_par_categorie,
            'depenses_par_categorie': depenses_par_categorie,
            'transactions_recentes': TransactionSerializer(transactions_recentes, many=True).data,
            'objectifs': objectifs,
            'alerts_budget': compute_budget_alerts(request.user),
        }
        cache.set(cache_key, payload, DASHBOARD_CACHE_TTL)
        return Response(payload)


# ─────────────────────────────────────────────────────────────────────────────
# BUDGET ALERTS
# ─────────────────────────────────────────────────────────────────────────────

class BudgetAlertView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        try:
            seuil = float(request.query_params.get('seuil', 80))
        except ValueError:
            seuil = 80
        seuil = max(0, min(100, seuil))
        alerts = compute_budget_alerts(request.user, seuil=seuil)
        return Response({
            'seuil': seuil,
            'count': len(alerts),
            'results': alerts,
        })


# ─────────────────────────────────────────────────────────────────────────────
# EXPORT PDF
# ─────────────────────────────────────────────────────────────────────────────

class ExportPDFView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request):
        date_debut  = request.data.get('date_debut')
        date_fin    = request.data.get('date_fin')
        entreprise_id = request.data.get('entreprise_id')
        type_export = request.data.get('type', 'transactions')
        signature_nom = request.data.get('signature_nom') or request.user.nom

        txns = apply_admin_scope(
            Transaction.objects.select_related('entreprise', 'user').all(),
            request.user
        )

        if date_debut:
            txns = txns.filter(date__gte=date_debut)
        if date_fin:
            txns = txns.filter(date__lte=date_fin)
        if entreprise_id:
            txns = txns.filter(entreprise_id=entreprise_id)

        log_action(
            request.user,
            'EXPORT_PDF',
            details={
                'type': type_export,
                'date_debut': date_debut,
                'date_fin': date_fin,
                'entreprise_id': entreprise_id,
            }
        )

        from django.http import HttpResponse
        pdf_content = generate_pdf_report(
            txns, type_export, date_debut, date_fin, signature_nom=signature_nom
        )
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="DeliverPro_Export_{date_debut}_{date_fin}.pdf"'
        return response


# ─────────────────────────────────────────────────────────────────────────────
# AUDIT LOG
# ─────────────────────────────────────────────────────────────────────────────

class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related('user').all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    filterset_fields = ['action', 'table_name']
    search_fields = ['action', 'user__nom']
    ordering = ['-created_at']
