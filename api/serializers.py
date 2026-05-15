"""
DeliverPro — Serializers DRF
"""
from rest_framework import serializers
from django.contrib.auth import authenticate
from .budget import get_objectif_progression
from .models import User, Entreprise, EntrepriseAccess, Transaction, Objectif, AuditLog


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
            user.is_staff = not bool(entreprise_ids)
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
# TRANSACTION SERIALIZERS
# ─────────────────────────────────────────────────────────────────────────────

class TransactionSerializer(serializers.ModelSerializer):
    entreprise_nom = serializers.CharField(source='entreprise.nom', read_only=True)
    user_nom       = serializers.CharField(source='user.nom',       read_only=True)

    class Meta:
        model  = Transaction
        fields = [
            'id', 'type', 'categorie', 'montant', 'label', 'description',
            'entreprise', 'entreprise_nom',
            'user', 'user_nom', 'date', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class TransactionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Transaction
        fields = ['type', 'categorie', 'montant', 'label', 'description', 'entreprise', 'user', 'date']

    def validate_montant(self, value):
        if value <= 0:
            raise serializers.ValidationError("Le montant doit être supérieur à 0.")
        return value


# ─────────────────────────────────────────────────────────────────────────────
# OBJECTIF SERIALIZER
# ─────────────────────────────────────────────────────────────────────────────

class ObjectifSerializer(serializers.ModelSerializer):
    progression = serializers.SerializerMethodField(read_only=True)
    entreprise_nom = serializers.CharField(source='entreprise.nom', read_only=True)

    class Meta:
        model  = Objectif
        fields = [
            'id', 'type', 'categorie', 'entreprise', 'entreprise_nom', 'montant', 'periode', 'label',
            'date_debut', 'date_fin', 'mois', 'annee',
            'seuil_alerte', 'notification_email', 'created_at', 'progression',
        ]
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        date_debut = attrs.get('date_debut', getattr(self.instance, 'date_debut', None))
        date_fin = attrs.get('date_fin', getattr(self.instance, 'date_fin', None))

        if date_debut or date_fin:
            if not date_debut or not date_fin:
                raise serializers.ValidationError("La date de debut et la date de fin sont obligatoires ensemble.")
            if date_fin < date_debut:
                raise serializers.ValidationError("La date de fin doit etre apres la date de debut.")
            attrs['periode'] = 'personnalise'

        obj_type = attrs.get('type', getattr(self.instance, 'type', None))
        if obj_type != 'depense':
            attrs['categorie'] = None
        if obj_type != 'revenu':
            attrs['entreprise'] = None

        entreprise = attrs.get('entreprise', getattr(self.instance, 'entreprise', None))
        entreprise_ids = self.context.get('entreprise_ids')
        if entreprise and entreprise_ids is not None and entreprise.id not in entreprise_ids:
            raise serializers.ValidationError("Entreprise hors perimetre autorise.")

        return attrs

    def validate_seuil_alerte(self, value):
        if value < 1 or value > 100:
            raise serializers.ValidationError("Le seuil d'alerte doit etre entre 1 et 100.")
        return value

    def get_progression(self, obj):
        entreprise_ids = self.context.get('entreprise_ids')
        return get_objectif_progression(obj, entreprise_ids=entreprise_ids)


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD SERIALIZERS
# ─────────────────────────────────────────────────────────────────────────────

class DashboardSerializer(serializers.Serializer):
    revenus_total      = serializers.DecimalField(max_digits=12, decimal_places=2)
    depenses_total     = serializers.DecimalField(max_digits=12, decimal_places=2)
    benefice_net       = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenus_par_jour   = serializers.ListField()
    depenses_par_jour  = serializers.ListField()


class AuditLogSerializer(serializers.ModelSerializer):
    user_nom = serializers.CharField(source='user.nom', read_only=True)

    class Meta:
        model  = AuditLog
        fields = ['id', 'user', 'user_nom', 'action', 'table_name', 'record_id', 'details', 'ip_address', 'created_at']
