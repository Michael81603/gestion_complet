"""
DeliverPro — Vues API (ViewSets + APIViews)
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncDate
from django.core.cache import cache
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, Entreprise, EntrepriseAccess, Commande, Transaction, Objectif, AuditLog
from .permissions import IsAdmin, IsLivreur, IsOwnerOrAdmin, IsAdminOrLivreur
from .serializers import (
    LoginSerializer, UserSerializer, UserCreateSerializer, UserUpdateSerializer,
    ChangePasswordSerializer, EntrepriseSerializer, EntrepriseListSerializer,
    CommandeSerializer, CommandeCreateSerializer,
    TransactionSerializer, TransactionCreateSerializer,
    ObjectifSerializer, AuditLogSerializer,
)
from .utils import log_action, generate_pdf_report
from .realtime import broadcast_event


DASHBOARD_CACHE_TTL = 60


def invalidate_dashboard_cache():
    """Invalidate dashboard-related cache after writes."""
    cache.clear()


def is_global_admin(user):
    """
    Global admins are never constrained by EntrepriseAccess rows.
    Staff/superusers keep full visibility by default.
    """
    return bool(user and user.is_authenticated and user.role == 'admin' and (user.is_staff or user.is_superuser))


def get_admin_scope_ids(user):
    """Renvoie les entreprises accessibles pour un admin; liste vide = accès global."""
    if not user.is_authenticated or user.role != 'admin':
        return []
    if is_global_admin(user):
        return []
    return list(
        EntrepriseAccess.objects.filter(user=user).values_list('entreprise_id', flat=True)
    )


def apply_admin_scope(qs, user, field='entreprise_id'):
    scope_ids = get_admin_scope_ids(user)
    if scope_ids:
        return qs.filter(**{f'{field}__in': scope_ids})
    return qs


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
        progression = ObjectifSerializer(
            obj, context={'entreprise_ids': get_admin_scope_ids(user)}
        ).data['progression']
        pct = progression['pourcentage']
        if progression['depasse']:
            alerts.append({
                'objectif_id': obj.id,
                'label': obj.label or obj.type,
                'niveau': 'depassement',
                'pourcentage': pct,
            })
        elif pct >= seuil:
            alerts.append({
                'objectif_id': obj.id,
                'label': obj.label or obj.type,
                'niveau': 'proche_limite',
                'pourcentage': pct,
            })
    return alerts


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

    def get_permissions(self):
        if self.action == 'update_location':
            return [IsAuthenticated(), IsLivreur()]
        return [IsAuthenticated(), IsAdmin()]

    def get_queryset(self):
        qs = super().get_queryset()
        scope_ids = get_admin_scope_ids(self.request.user)
        if not scope_ids:
            return qs
        scoped_user_ids = set(
            EntrepriseAccess.objects.filter(entreprise_id__in=scope_ids).values_list('user_id', flat=True)
        )
        scoped_user_ids.update(
            Commande.objects.filter(entreprise_id__in=scope_ids, livreur__isnull=False).values_list('livreur_id', flat=True)
        )
        return qs.filter(Q(role='admin') | Q(id__in=scoped_user_ids)).distinct()

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

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        user = self.get_object()
        cmds = apply_admin_scope(Commande.objects.filter(livreur=user), request.user)
        total_paiements = Transaction.objects.filter(
            type='revenu',
            commande__in=cmds
        ).aggregate(t=Sum('montant'))['t'] or Decimal('0')
        return Response({
            'total_commandes':  cmds.count(),
            'livrees':          cmds.filter(statut__in=['livrée', 'payée']).count(),
            'en_cours':         cmds.filter(statut='en cours').count(),
            'en_attente':       cmds.filter(statut='en attente').count(),
            'total_paiements':  total_paiements,
        })

    @action(detail=False, methods=['post'])
    def update_location(self, request):
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        if latitude is None or longitude is None:
            return Response({'error': 'latitude et longitude sont requis.'}, status=400)
        try:
            latitude = Decimal(str(latitude))
            longitude = Decimal(str(longitude))
        except Exception:
            return Response({'error': 'latitude/longitude invalides.'}, status=400)
        if latitude < Decimal('-90') or latitude > Decimal('90'):
            return Response({'error': 'latitude hors plage.'}, status=400)
        if longitude < Decimal('-180') or longitude > Decimal('180'):
            return Response({'error': 'longitude hors plage.'}, status=400)
        request.user.last_latitude = latitude
        request.user.last_longitude = longitude
        request.user.last_location_at = timezone.now()
        request.user.save(update_fields=['last_latitude', 'last_longitude', 'last_location_at', 'updated_at'])
        log_action(request.user, 'UPDATE_LOCATION', 'user', request.user.id)
        broadcast_event(
            'livreur.location',
            {
                'livreur_id': request.user.id,
                'latitude': float(latitude),
                'longitude': float(longitude),
                'timestamp': request.user.last_location_at.isoformat(),
            },
            livreur_id=request.user.id,
        )
        return Response({'detail': 'Position mise à jour.'})

    @action(detail=False, methods=['get'])
    def livreurs_positions(self, request):
        livreurs = self.get_queryset().filter(role='livreur').exclude(
            last_latitude__isnull=True, last_longitude__isnull=True
        )
        data = [
            {
                'id': u.id,
                'nom': u.nom,
                'latitude': float(u.last_latitude),
                'longitude': float(u.last_longitude),
                'last_location_at': u.last_location_at,
            }
            for u in livreurs
        ]
        return Response(data)


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
        if get_admin_scope_ids(self.request.user):
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
        log_action(self.request.user, 'DELETE_ENTREPRISE', 'entreprise', instance.id)
        instance.delete()
        invalidate_dashboard_cache()
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
        cache_key = f"ent_dash:{request.user.id}:{ent.id}:{periode}"
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        stats = ent.get_stats()
        cmds_qs = Commande.objects.filter(entreprise=ent)
        txns_qs = Transaction.objects.filter(entreprise=ent)
        if date_debut:
            cmds_qs = cmds_qs.filter(date__gte=date_debut)
            txns_qs = txns_qs.filter(date__gte=date_debut)

        cmds = cmds_qs.order_by('-created_at')[:10]
        rev_par_jour = (
            txns_qs.filter(type='revenu')
            .annotate(jour=TruncDate('date'))
            .values('jour')
            .annotate(total=Sum('montant'))
            .order_by('jour')
        )
        dep_par_jour = (
            txns_qs.filter(type='depense')
            .annotate(jour=TruncDate('date'))
            .values('jour')
            .annotate(total=Sum('montant'))
            .order_by('jour')
        )
        cmd_par_statut = list(
            cmds_qs.values('statut').annotate(total=Count('id')).order_by('statut')
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
            'commandes_recentes': CommandeSerializer(cmds, many=True).data,
            'revenus_par_jour': [{'date': str(r['jour']), 'total': float(r['total'])} for r in rev_par_jour],
            'depenses_par_jour': [{'date': str(d['jour']), 'total': float(d['total'])} for d in dep_par_jour],
            'commandes_par_statut': cmd_par_statut,
            'alerts_budget': compute_budget_alerts(request.user),
        }
        cache.set(cache_key, payload, DASHBOARD_CACHE_TTL)
        return Response(payload)


# ─────────────────────────────────────────────────────────────────────────────
# COMMANDE
# ─────────────────────────────────────────────────────────────────────────────

class CommandeViewSet(viewsets.ModelViewSet):
    queryset = Commande.objects.select_related('entreprise', 'livreur').all()
    filterset_fields = ['statut', 'entreprise', 'livreur']
    search_fields = ['client_nom', 'adresse', 'telephone']
    ordering_fields = ['date', 'created_at', 'prix']

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAuthenticated(), IsAdminOrLivreur()]
        if self.action in ('update', 'partial_update', 'demarrer', 'livrer', 'payer') and self.request.user.role == 'livreur':
            return [IsAuthenticated(), IsOwnerOrAdmin()]
        return [IsAuthenticated(), IsAdmin()]

    def get_serializer_class(self):
        if self.action == 'create':
            return CommandeCreateSerializer
        return CommandeSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        # Livreur ne voit que ses commandes
        if user.role == 'livreur':
            qs = qs.filter(livreur=user)
        if user.role == 'admin':
            qs = apply_admin_scope(qs, user)
        # Filtres date
        date_debut = self.request.query_params.get('date_debut')
        date_fin   = self.request.query_params.get('date_fin')
        if date_debut:
            qs = qs.filter(date__gte=date_debut)
        if date_fin:
            qs = qs.filter(date__lte=date_fin)
        return qs

    def perform_create(self, serializer):
        cmd = serializer.save()
        invalidate_dashboard_cache()
        log_action(self.request.user, 'CREATE_COMMANDE', 'commande', cmd.id)
        broadcast_event(
            'commande.created',
            {
                'id': cmd.id,
                'statut': cmd.statut,
                'entreprise_id': cmd.entreprise_id,
                'livreur_id': cmd.livreur_id,
            },
            entreprise_id=cmd.entreprise_id,
            livreur_id=cmd.livreur_id,
        )

    def perform_update(self, serializer):
        cmd = serializer.save()
        invalidate_dashboard_cache()
        log_action(self.request.user, 'UPDATE_COMMANDE', 'commande', cmd.id)
        broadcast_event(
            'commande.updated',
            {'id': cmd.id, 'statut': cmd.statut},
            entreprise_id=cmd.entreprise_id,
            livreur_id=cmd.livreur_id,
        )

    def perform_destroy(self, instance):
        cmd_id = instance.id
        ent_id = instance.entreprise_id
        liv_id = instance.livreur_id
        log_action(self.request.user, 'DELETE_COMMANDE', 'commande', cmd_id)
        instance.delete()
        invalidate_dashboard_cache()
        broadcast_event(
            'commande.deleted',
            {'id': cmd_id},
            entreprise_id=ent_id,
            livreur_id=liv_id,
        )

    @action(detail=True, methods=['post'])
    def demarrer(self, request, pk=None):
        """Livreur démarre la livraison."""
        cmd = self.get_object()
        if cmd.statut != 'en attente':
            return Response({'error': 'La commande doit être en attente.'}, status=400)
        cmd.statut = 'en cours'
        cmd.date_demarrage = timezone.now()
        cmd.save()
        invalidate_dashboard_cache()
        log_action(request.user, 'DEMARRER_LIVRAISON', 'commande', cmd.id)
        broadcast_event(
            'commande.updated',
            {'id': cmd.id, 'statut': cmd.statut},
            entreprise_id=cmd.entreprise_id,
            livreur_id=cmd.livreur_id,
        )
        return Response(CommandeSerializer(cmd).data)

    @action(detail=True, methods=['post'])
    def livrer(self, request, pk=None):
        """Livreur marque comme livrée."""
        cmd = self.get_object()
        if cmd.statut != 'en cours':
            return Response({'error': 'La commande doit être en cours.'}, status=400)
        cmd.statut = 'livrée'
        cmd.save()
        invalidate_dashboard_cache()
        log_action(request.user, 'LIVRAISON_EFFECTUEE', 'commande', cmd.id)
        broadcast_event(
            'commande.updated',
            {'id': cmd.id, 'statut': cmd.statut, 'date_livraison': cmd.date_livraison.isoformat() if cmd.date_livraison else None},
            entreprise_id=cmd.entreprise_id,
            livreur_id=cmd.livreur_id,
        )
        return Response(CommandeSerializer(cmd).data)

    @action(detail=True, methods=['post'])
    def payer(self, request, pk=None):
        """Livreur enregistre le paiement reçu."""
        cmd = self.get_object()
        if cmd.statut != 'livrée':
            return Response({'error': 'La commande doit être livrée avant de recevoir le paiement.'}, status=400)
        cmd.statut = 'payée'
        cmd.save()  # Déclenche _create_transactions()
        invalidate_dashboard_cache()
        log_action(request.user, 'PAIEMENT_RECU', 'commande', cmd.id, {'montant': str(cmd.prix)})
        broadcast_event(
            'commande.updated',
            {'id': cmd.id, 'statut': cmd.statut, 'date_paiement': cmd.date_paiement.isoformat() if cmd.date_paiement else None},
            entreprise_id=cmd.entreprise_id,
            livreur_id=cmd.livreur_id,
        )
        return Response(CommandeSerializer(cmd).data)


# ─────────────────────────────────────────────────────────────────────────────
# TRANSACTION
# ─────────────────────────────────────────────────────────────────────────────

class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.select_related('entreprise', 'user', 'commande').all()
    permission_classes = [IsAuthenticated, IsAdmin]
    filterset_fields = ['type', 'entreprise']
    search_fields = ['label']
    ordering_fields = ['date', 'montant']

    def get_permissions(self):
        if self.action == 'my_history':
            return [IsAuthenticated(), IsLivreur()]
        if self.action in ('ajouter_revenu', 'ajouter_depense'):
            return [IsAuthenticated(), IsAdmin()]
        return [IsAuthenticated(), IsAdmin()]

    def get_serializer_class(self):
        if self.action == 'create':
            return TransactionCreateSerializer
        return TransactionSerializer

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
        txn = serializer.save()
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
            livreur_id=txn.user_id,
        )

    def _create_manual_transaction(self, request, tx_type):
        payload = request.data.copy()
        payload['type'] = tx_type
        scope_ids = get_admin_scope_ids(request.user)
        ent_id = payload.get('entreprise')
        if scope_ids and ent_id and int(ent_id) not in scope_ids:
            return Response({'error': "Entreprise hors périmètre autorisé."}, status=403)
        serializer = TransactionCreateSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        txn = serializer.save()
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
            livreur_id=txn.user_id,
        )
        return Response(TransactionSerializer(txn).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='ajouter-revenu')
    def ajouter_revenu(self, request):
        return self._create_manual_transaction(request, 'revenu')

    @action(detail=False, methods=['post'], url_path='ajouter-depense')
    def ajouter_depense(self, request):
        return self._create_manual_transaction(request, 'depense')

    @action(detail=False, methods=['get'], url_path='my-history')
    def my_history(self, request):
        qs = Transaction.objects.select_related('entreprise', 'user', 'commande').filter(
            Q(user=request.user) | Q(commande__livreur=request.user)
        ).distinct().order_by('-date', '-created_at')
        tx_type = request.query_params.get('type')
        if tx_type in ('revenu', 'depense'):
            qs = qs.filter(type=tx_type)
        date_debut = request.query_params.get('date_debut')
        date_fin = request.query_params.get('date_fin')
        if date_debut:
            qs = qs.filter(date__gte=date_debut)
        if date_fin:
            qs = qs.filter(date__lte=date_fin)
        return Response(TransactionSerializer(qs, many=True).data)


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
        scope_part = ','.join(str(i) for i in sorted(scope_ids)) if scope_ids else 'all'
        cache_key = f"global_dash:{request.user.id}:{periode}:{scope_part}"
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        today = date.today()
        date_debut = get_period_start(periode, today)

        txns = apply_admin_scope(Transaction.objects.filter(date__gte=date_debut), request.user)
        revenus  = txns.filter(type='revenu').aggregate(t=Sum('montant'))['t'] or Decimal('0')
        depenses = txns.filter(type='depense').aggregate(t=Sum('montant'))['t'] or Decimal('0')

        # Commandes
        cmds = apply_admin_scope(Commande.objects.all(), request.user)
        nb_statuts = cmds.values('statut').annotate(n=Count('id'))
        statut_map = {s['statut']: s['n'] for s in nb_statuts}

        # Revenu par jour (30 derniers jours)
        rev_par_jour = (
            apply_admin_scope(
                Transaction.objects.filter(type='revenu', date__gte=today - timedelta(days=30)),
                request.user,
            )
            .annotate(jour=TruncDate('date'))
            .values('jour')
            .annotate(total=Sum('montant'))
            .order_by('jour')
        )
        dep_par_jour = (
            apply_admin_scope(
                Transaction.objects.filter(type='depense', date__gte=today - timedelta(days=30)),
                request.user,
            )
            .annotate(jour=TruncDate('date'))
            .values('jour')
            .annotate(total=Sum('montant'))
            .order_by('jour')
        )

        # Stats par entreprise
        entreprises_qs = apply_admin_scope(Entreprise.objects.all(), request.user, field='id')
        entreprises_stats = []
        for ent in entreprises_qs:
            s = ent.get_stats()
            entreprises_stats.append({
                'id': ent.id, 'nom': ent.nom,
                'revenus': s['revenus'], 'depenses': s['depenses'],
                'benefice': s['benefice'], 'nb_commandes': s['nb_commandes'],
            })

        commandes_par_entreprise = list(
            cmds.values('entreprise__id', 'entreprise__nom').annotate(total=Count('id')).order_by('-total')
        )
        objectifs = ObjectifSerializer(
            Objectif.objects.all(),
            many=True,
            context={'entreprise_ids': scope_ids},
        ).data
        payload = {
            'periode':         periode,
            'revenus_total':   revenus,
            'depenses_total':  depenses,
            'benefice_net':    revenus - depenses,
            'nb_commandes':    cmds.count(),
            'nb_en_attente':   statut_map.get('en attente', 0),
            'nb_en_cours':     statut_map.get('en cours', 0),
            'nb_livrees':      statut_map.get('livrée', 0),
            'nb_payees':       statut_map.get('payée', 0),
            'revenus_par_jour': [
                {'date': str(r['jour']), 'total': float(r['total'])} for r in rev_par_jour
            ],
            'depenses_par_jour': [
                {'date': str(d['jour']), 'total': float(d['total'])} for d in dep_par_jour
            ],
            'entreprises_stats': entreprises_stats,
            'commandes_par_entreprise': commandes_par_entreprise,
            'objectifs': objectifs,
            'alerts_budget': compute_budget_alerts(request.user),
        }
        cache.set(cache_key, payload, DASHBOARD_CACHE_TTL)
        return Response(payload)


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD LIVREUR
# ─────────────────────────────────────────────────────────────────────────────

class DashboardLivreurView(APIView):
    permission_classes = [IsAuthenticated, IsLivreur]

    def get(self, request):
        user = request.user
        cmds = Commande.objects.filter(livreur=user)
        revenus_qs = Transaction.objects.filter(type='revenu').filter(
            Q(user=user) | Q(commande__in=cmds)
        ).distinct()
        total_paiements = revenus_qs.aggregate(t=Sum('montant'))['t'] or Decimal('0')
        revenus_par_jour = (
            revenus_qs.filter(date__gte=date.today() - timedelta(days=30))
            .annotate(jour=TruncDate('date'))
            .values('jour')
            .annotate(total=Sum('montant'))
            .order_by('jour')
        )
        dernieres_transactions = Transaction.objects.filter(
            Q(user=user) | Q(commande__livreur=user)
        ).select_related('entreprise', 'commande').distinct().order_by('-created_at')[:20]
        return Response({
            'total_commandes':  cmds.count(),
            'en_attente':       cmds.filter(statut='en attente').count(),
            'en_cours':         cmds.filter(statut='en cours').count(),
            'livrees':          cmds.filter(statut='livrée').count(),
            'payees':           cmds.filter(statut='payée').count(),
            'total_paiements':  total_paiements,
            'revenus_par_jour': [
                {'date': str(r['jour']), 'total': float(r['total'])} for r in revenus_par_jour
            ],
            'historique_transactions': TransactionSerializer(dernieres_transactions, many=True).data,
        })


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
        livreur_id  = request.data.get('livreur_id')
        type_export = request.data.get('type', 'commandes')  # commandes | transactions | complet
        signature_nom = request.data.get('signature_nom') or request.user.nom

        cmds = apply_admin_scope(
            Commande.objects.select_related('entreprise', 'livreur').all(),
            request.user
        )
        txns = apply_admin_scope(
            Transaction.objects.select_related('entreprise', 'user').all(),
            request.user
        )

        if date_debut:
            cmds = cmds.filter(date__gte=date_debut)
            txns = txns.filter(date__gte=date_debut)
        if date_fin:
            cmds = cmds.filter(date__lte=date_fin)
            txns = txns.filter(date__lte=date_fin)
        if entreprise_id:
            cmds = cmds.filter(entreprise_id=entreprise_id)
            txns = txns.filter(entreprise_id=entreprise_id)
        if livreur_id:
            cmds = cmds.filter(livreur_id=livreur_id)
            txns = txns.filter(Q(user_id=livreur_id) | Q(commande__livreur_id=livreur_id))

        log_action(
            request.user,
            'EXPORT_PDF',
            details={
                'type': type_export,
                'date_debut': date_debut,
                'date_fin': date_fin,
                'entreprise_id': entreprise_id,
                'livreur_id': livreur_id,
            }
        )

        from django.http import HttpResponse
        pdf_content = generate_pdf_report(
            cmds, txns, type_export, date_debut, date_fin, signature_nom=signature_nom
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
