"""
Script de gestion : seed_data
Usage: python manage.py seed_data
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal
import datetime


class Command(BaseCommand):
    help = 'Insère des données de démonstration dans la base de données'

    def handle(self, *args, **options):
        from api.models import User, Entreprise, EntrepriseAccess, Transaction, Objectif

        self.stdout.write(self.style.WARNING('🌱 Insertion des données de démonstration...'))

        # ── Users ──────────────────────────────────────────────────────────
        admin = (
            User.objects.filter(email='rakezyadiams@gmail.com').first()
            or User.objects.filter(email='admin@deliverpro.com').first()
        )
        if admin:
            admin.email = 'rakezyadiams@gmail.com'
            admin.nom = admin.nom or 'Admin Principal'
            admin.role = 'admin'
            admin.is_staff = True
        else:
            admin = User(
                email='rakezyadiams@gmail.com',
                nom='Admin Principal',
                role='admin',
                is_staff=True,
            )
        admin.set_password('Admin123!')
        admin.save()

        self.stdout.write('  ✅ Administrateur créé')

        # ── Entreprises ────────────────────────────────────────────────────
        ent1, _ = Entreprise.objects.get_or_create(nom='TechShop Paris',  defaults={'adresse': '12 Rue de la Paix, Paris 1', 'telephone': '01 23 45 67 89'})
        ent2, _ = Entreprise.objects.get_or_create(nom='Mode & Style',    defaults={'adresse': '45 Av. Victor Hugo, Lyon',    'telephone': '04 56 78 90 12'})
        ent3, _ = Entreprise.objects.get_or_create(nom='Électro Plus',    defaults={'adresse': '78 Bd. Pasteur, Marseille',    'telephone': '04 91 23 45 67'})
        EntrepriseAccess.objects.get_or_create(user=admin, entreprise=ent1)
        EntrepriseAccess.objects.get_or_create(user=admin, entreprise=ent2)
        EntrepriseAccess.objects.get_or_create(user=admin, entreprise=ent3)
        self.stdout.write('  ✅ Entreprises créées')

        # ── Transactions financières ───────────────────────────────────────
        today = datetime.date.today()
        transactions_data = [
            {'entreprise': ent1, 'type': 'revenu', 'categorie': 'vente', 'label': 'Ventes produits TechShop', 'montant': Decimal('4200.00'), 'date': today - datetime.timedelta(days=20)},
            {'entreprise': ent1, 'type': 'depense', 'categorie': 'fournitures', 'label': 'Achat stock accessoires', 'montant': Decimal('1250.00'), 'date': today - datetime.timedelta(days=18)},
            {'entreprise': ent2, 'type': 'revenu', 'categorie': 'vente', 'label': 'Collection Mode & Style', 'montant': Decimal('3150.00'), 'date': today - datetime.timedelta(days=12)},
            {'entreprise': ent2, 'type': 'depense', 'categorie': 'marketing', 'label': 'Campagne reseaux sociaux', 'montant': Decimal('540.00'), 'date': today - datetime.timedelta(days=9)},
            {'entreprise': ent3, 'type': 'revenu', 'categorie': 'prestation', 'label': 'Installation et maintenance', 'montant': Decimal('2800.00'), 'date': today - datetime.timedelta(days=6)},
            {'entreprise': ent3, 'type': 'depense', 'categorie': 'maintenance', 'label': 'Pieces de rechange', 'montant': Decimal('760.00'), 'date': today - datetime.timedelta(days=4)},
            {'entreprise': ent1, 'type': 'depense', 'categorie': 'salaire', 'label': 'Salaires equipe', 'montant': Decimal('1800.00'), 'date': today},
        ]

        for data in transactions_data:
            Transaction.objects.get_or_create(
                entreprise=data['entreprise'],
                label=data['label'],
                date=data['date'],
                defaults={**data, 'user': admin},
            )

        self.stdout.write('  ✅ Transactions créées')

        # ── Objectifs ──────────────────────────────────────────────────────
        Objectif.objects.get_or_create(
            type='revenu',
            defaults={'montant': Decimal('5000'), 'periode': 'mensuel', 'label': 'Objectif revenu mensuel', 'mois': today.month, 'annee': today.year}
        )
        Objectif.objects.get_or_create(
            type='depense',
            defaults={'montant': Decimal('2000'), 'periode': 'mensuel', 'label': 'Budget dépenses max', 'mois': today.month, 'annee': today.year}
        )
        self.stdout.write('  ✅ Objectifs créés')

        self.stdout.write(self.style.SUCCESS('\n✨ Données de démonstration insérées avec succès!\n'))
        self.stdout.write(self.style.SUCCESS('👤 Admin     : rakezyadiams@gmail.com / Admin123!'))
