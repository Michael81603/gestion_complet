"""
Commande de gestion : seed_data
Usage: python manage.py seed_data
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal
import datetime


class Command(BaseCommand):
    help = 'Insère des données de démonstration dans la base de données'

    def handle(self, *args, **options):
        from api.models import User, Entreprise, EntrepriseAccess, Commande, Transaction, Objectif

        self.stdout.write(self.style.WARNING('🌱 Insertion des données de démonstration...'))

        # ── Users ──────────────────────────────────────────────────────────
        admin, _ = User.objects.get_or_create(
            email='admin@deliverpro.com',
            defaults={'nom': 'Admin Principal', 'role': 'admin', 'is_staff': True}
        )
        admin.set_password('Admin123!')
        admin.save()

        livreur1, _ = User.objects.get_or_create(
            email='jean@deliverpro.com',
            defaults={'nom': 'Jean Dupont', 'role': 'livreur', 'telephone': '06 12 34 56 78'}
        )
        livreur1.set_password('Livr123!')
        livreur1.save()

        livreur2, _ = User.objects.get_or_create(
            email='marie@deliverpro.com',
            defaults={'nom': 'Marie Martin', 'role': 'livreur', 'telephone': '06 98 76 54 32'}
        )
        livreur2.set_password('Livr123!')
        livreur2.save()

        self.stdout.write('  ✅ Utilisateurs créés')

        # ── Entreprises ────────────────────────────────────────────────────
        ent1, _ = Entreprise.objects.get_or_create(nom='TechShop Paris',  defaults={'adresse': '12 Rue de la Paix, Paris 1', 'telephone': '01 23 45 67 89'})
        ent2, _ = Entreprise.objects.get_or_create(nom='Mode & Style',    defaults={'adresse': '45 Av. Victor Hugo, Lyon',    'telephone': '04 56 78 90 12'})
        ent3, _ = Entreprise.objects.get_or_create(nom='Électro Plus',    defaults={'adresse': '78 Bd. Pasteur, Marseille',    'telephone': '04 91 23 45 67'})
        EntrepriseAccess.objects.get_or_create(user=admin, entreprise=ent1)
        EntrepriseAccess.objects.get_or_create(user=admin, entreprise=ent2)
        EntrepriseAccess.objects.get_or_create(user=admin, entreprise=ent3)
        self.stdout.write('  ✅ Entreprises créées')

        # ── Commandes ──────────────────────────────────────────────────────
        today = datetime.date.today()
        commandes_data = [
            {'entreprise': ent1, 'livreur': livreur1, 'client_nom': 'Pierre Martin', 'adresse': '3 Rue du Moulin, Paris 15', 'telephone': '06 11 22 33 44', 'prix': Decimal('180.00'), 'cout_livraison': Decimal('15.00'), 'statut': 'payée', 'date': today - datetime.timedelta(days=30)},
            {'entreprise': ent1, 'livreur': livreur1, 'client_nom': 'Sophie Bernard', 'adresse': '7 Allée des Roses, Paris 8', 'telephone': '06 55 66 77 88', 'prix': Decimal('95.00'), 'cout_livraison': Decimal('12.00'), 'statut': 'livrée', 'date': today - datetime.timedelta(days=15)},
            {'entreprise': ent2, 'livreur': livreur2, 'client_nom': 'Marc Leroy', 'adresse': '22 Rue Carnot, Lyon 3', 'telephone': '07 11 22 33 44', 'prix': Decimal('240.00'), 'cout_livraison': Decimal('20.00'), 'statut': 'en cours', 'date': today - datetime.timedelta(days=5)},
            {'entreprise': ent3, 'livreur': livreur1, 'client_nom': 'Aline Petit', 'adresse': '15 Cours Belsunce, Marseille', 'telephone': '06 33 44 55 66', 'prix': Decimal('320.00'), 'cout_livraison': Decimal('25.00'), 'statut': 'en attente', 'date': today},
            {'entreprise': ent2, 'livreur': livreur2, 'client_nom': 'Lucas Morel', 'adresse': '9 Rue de la République, Lyon 1', 'telephone': '07 99 88 77 66', 'prix': Decimal('150.00'), 'cout_livraison': Decimal('18.00'), 'statut': 'payée', 'date': today - datetime.timedelta(days=20)},
        ]

        for data in commandes_data:
            if not Commande.objects.filter(client_nom=data['client_nom'], date=data['date']).exists():
                Commande.objects.create(**data)

        self.stdout.write('  ✅ Commandes créées')

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
        self.stdout.write(self.style.SUCCESS('👤 Admin     : admin@deliverpro.com / Admin123!'))
        self.stdout.write(self.style.SUCCESS('🚚 Livreur 1 : jean@deliverpro.com  / Livr123!'))
        self.stdout.write(self.style.SUCCESS('🚚 Livreur 2 : marie@deliverpro.com / Livr123!'))
