"""
DeliverPro — Serializers DRF
"""
from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import User, Entreprise, EntrepriseAccess, Commande, Transaction, Objectif, AuditLog


# ─────────────────────────────────────────────────────────────────────────────
# AUTH SERIALIZERS
# ─────────────────────────────────────────────────────────────────────────────

class LoginSerializer(serializers.Serializer):
    email    = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(email=data['email'], password=data['password'])
        if not user:
            raise serializers.ValidationError("Email ou mot de passe incorrect.")
        if not user.is_active:
            raise serializers.ValidationError("Ce compte est désactivé.")
        data['user'] = user
        return data


class UserSerializer(serializers.ModelSerializer):
    entreprise_ids = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = User
        fields = [
            'id', 'nom', 'email', 'role', 'telephone', 'actif',
            'last_latitude', 'last_longitude', 'last_location_at',
            'entreprise_ids', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_entreprise_ids(self, obj):
        return list(obj.entreprise_accesses.values_list('entreprise_id', flat=True))


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    entreprise_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        write_only=True,
        required=False
    )

    class Meta:
        model  = User
        fields = ['id', 'nom', 'email', 'password', 'role', 'telephone', 'entreprise_ids']

    def create(self, validated_data):
        password = validated_data.pop('password')
        entreprise_ids = validated_data.pop('entreprise_ids', [])
        user = User(**validated_data)
        if user.role == 'admin':
            user.is_staff = True
        user.set_password(password)
        user.save()
        if entreprise_ids:
            access_rows = [
                EntrepriseAccess(user=user, entreprise_id=ent_id)
                for ent_id in set(entreprise_ids)
            ]
            EntrepriseAccess.objects.bulk_create(access_rows, ignore_conflicts=True)
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    entreprise_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        write_only=True,
        required=False
    )

    class Meta:
        model  = User
        fields = ['nom', 'telephone', 'actif', 'entreprise_ids']

    def validate(self, attrs):
        if 'entreprise_ids' in attrs:
            actor = self.context.get('request').user if self.context.get('request') else None
            if not actor or actor.role != 'admin':
                raise serializers.ValidationError("Seul un admin peut modifier les accès entreprise.")
        return attrs

    def update(self, instance, validated_data):
        entreprise_ids = validated_data.pop('entreprise_ids', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if entreprise_ids is not None:
            EntrepriseAccess.objects.filter(user=instance).exclude(entreprise_id__in=entreprise_ids).delete()
            access_rows = [
                EntrepriseAccess(user=instance, entreprise_id=ent_id)
                for ent_id in set(entreprise_ids)
            ]
            EntrepriseAccess.objects.bulk_create(access_rows, ignore_conflicts=True)
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=6)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Mot de passe actuel incorrect.")
        return value


# ─────────────────────────────────────────────────────────────────────────────
# ENTREPRISE SERIALIZERS
# ─────────────────────────────────────────────────────────────────────────────

class EntrepriseSerializer(serializers.ModelSerializer):
    stats = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = Entreprise
        fields = ['id', 'nom', 'adresse', 'telephone', 'date_creation', 'created_at', 'stats']
        read_only_fields = ['id', 'created_at']

    def get_stats(self, obj):
        return obj.get_stats()


class EntrepriseListSerializer(serializers.ModelSerializer):
    """Version allégée pour les listes."""
    class Meta:
        model  = Entreprise
        fields = ['id', 'nom', 'adresse', 'telephone']


# ─────────────────────────────────────────────────────────────────────────────
# COMMANDE SERIALIZERS
# ─────────────────────────────────────────────────────────────────────────────

class CommandeSerializer(serializers.ModelSerializer):
    entreprise_nom = serializers.CharField(source='entreprise.nom', read_only=True)
    livreur_nom    = serializers.CharField(source='livreur.nom',    read_only=True)

    class Meta:
        model  = Commande
        fields = [
            'id', 'entreprise', 'entreprise_nom',
            'livreur', 'livreur_nom',
            'client_nom', 'adresse', 'latitude', 'longitude', 'telephone',
            'prix', 'cout_livraison', 'depense',
            'statut', 'date', 'date_demarrage', 'date_livraison', 'date_paiement',
            'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'date_demarrage', 'date_livraison', 'date_paiement', 'created_at', 'updated_at']

    def validate(self, data):
        statut = data.get('statut', getattr(self.instance, 'statut', 'en attente'))
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        if latitude is not None and (latitude < -90 or latitude > 90):
            raise serializers.ValidationError("La latitude doit être comprise entre -90 et 90.")
        if longitude is not None and (longitude < -180 or longitude > 180):
            raise serializers.ValidationError("La longitude doit être comprise entre -180 et 180.")
        # Règle: ne peut être payée que si livrée
        if statut == 'payée':
            instance_statut = getattr(self.instance, 'statut', 'en attente')
            if instance_statut not in ('livrée', 'payée') and data.get('statut') == 'payée':
                raise serializers.ValidationError(
                    "Une commande doit être livrée avant d'être marquée comme payée."
                )
        return data


class CommandeCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Commande
        fields = [
            'entreprise', 'livreur', 'client_nom', 'adresse', 'latitude', 'longitude',
            'telephone', 'prix', 'cout_livraison', 'depense',
            'statut', 'date', 'notes',
        ]

    def validate(self, attrs):
        latitude = attrs.get('latitude')
        longitude = attrs.get('longitude')
        if latitude is not None and (latitude < -90 or latitude > 90):
            raise serializers.ValidationError("La latitude doit être comprise entre -90 et 90.")
        if longitude is not None and (longitude < -180 or longitude > 180):
            raise serializers.ValidationError("La longitude doit être comprise entre -180 et 180.")
        return attrs


# ─────────────────────────────────────────────────────────────────────────────
# TRANSACTION SERIALIZERS
# ─────────────────────────────────────────────────────────────────────────────

class TransactionSerializer(serializers.ModelSerializer):
    entreprise_nom = serializers.CharField(source='entreprise.nom', read_only=True)
    user_nom       = serializers.CharField(source='user.nom',       read_only=True)

    class Meta:
        model  = Transaction
        fields = [
            'id', 'type', 'montant', 'label',
            'commande', 'entreprise', 'entreprise_nom',
            'user', 'user_nom', 'date', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class TransactionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Transaction
        fields = ['type', 'montant', 'label', 'commande', 'entreprise', 'user', 'date']

    def validate_montant(self, value):
        if value <= 0:
            raise serializers.ValidationError("Le montant doit être supérieur à 0.")
        return value


# ─────────────────────────────────────────────────────────────────────────────
# OBJECTIF SERIALIZER
# ─────────────────────────────────────────────────────────────────────────────

class ObjectifSerializer(serializers.ModelSerializer):
    progression = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = Objectif
        fields = ['id', 'type', 'montant', 'periode', 'label', 'mois', 'annee', 'created_at', 'progression']
        read_only_fields = ['id', 'created_at']

    def get_progression(self, obj):
        from django.db.models import Sum
        qs = Transaction.objects.all()
        entreprise_ids = self.context.get('entreprise_ids')
        if entreprise_ids:
            qs = qs.filter(entreprise_id__in=entreprise_ids)
        if obj.mois:
            qs = qs.filter(date__month=obj.mois)
        if obj.annee:
            qs = qs.filter(date__year=obj.annee)
        total = qs.filter(type=obj.type).aggregate(t=Sum('montant'))['t'] or 0
        pct = float(total / obj.montant * 100) if obj.montant else 0
        return {
            'total':      float(total),
            'objectif':   float(obj.montant),
            'pourcentage': round(pct, 1),
            'depasse':    total > obj.montant,
        }


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD SERIALIZERS
# ─────────────────────────────────────────────────────────────────────────────

class DashboardSerializer(serializers.Serializer):
    revenus_total      = serializers.DecimalField(max_digits=12, decimal_places=2)
    depenses_total     = serializers.DecimalField(max_digits=12, decimal_places=2)
    benefice_net       = serializers.DecimalField(max_digits=12, decimal_places=2)
    nb_commandes       = serializers.IntegerField()
    nb_en_attente      = serializers.IntegerField()
    nb_en_cours        = serializers.IntegerField()
    nb_livrees         = serializers.IntegerField()
    nb_payees          = serializers.IntegerField()
    revenus_par_jour   = serializers.ListField()
    depenses_par_jour  = serializers.ListField()


class AuditLogSerializer(serializers.ModelSerializer):
    user_nom = serializers.CharField(source='user.nom', read_only=True)

    class Meta:
        model  = AuditLog
        fields = ['id', 'user', 'user_nom', 'action', 'table_name', 'record_id', 'details', 'ip_address', 'created_at']
