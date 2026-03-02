from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from api.models import User, Entreprise, Commande, Transaction, Objectif


class APIFeaturesTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='admin@test.com',
            password='Admin123!',
            nom='Admin',
            role='admin',
            is_staff=True,
        )
        self.livreur = User.objects.create_user(
            email='livreur@test.com',
            password='Livreur123!',
            nom='Livreur One',
            role='livreur',
        )
        self.other_livreur = User.objects.create_user(
            email='livreur2@test.com',
            password='Livreur123!',
            nom='Livreur Two',
            role='livreur',
        )
        self.ent = Entreprise.objects.create(nom='Entreprise Test')
        self.commande = Commande.objects.create(
            entreprise=self.ent,
            livreur=self.livreur,
            client_nom='Client',
            adresse='Adresse',
            prix=Decimal('100.00'),
            cout_livraison=Decimal('10.00'),
            statut='en attente',
        )

    def _auth(self, user):
        token = str(RefreshToken.for_user(user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_livreur_can_demarrer_own_commande(self):
        self._auth(self.livreur)
        url = f'/api/commandes/{self.commande.id}/demarrer/'
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.statut, 'en cours')
        self.assertIsNotNone(self.commande.date_demarrage)

    def test_livreur_cannot_demarrer_other_commande(self):
        self._auth(self.other_livreur)
        url = f'/api/commandes/{self.commande.id}/demarrer/'
        response = self.client.post(url)
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_admin_can_add_manual_revenu(self):
        self._auth(self.admin)
        url = '/api/transactions/ajouter-revenu/'
        payload = {
            'montant': '250.00',
            'label': 'Revenu manuel test',
            'entreprise': self.ent.id,
            'user': self.livreur.id,
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Transaction.objects.count(), 1)
        txn = Transaction.objects.first()
        self.assertEqual(txn.type, 'revenu')

    def test_budget_alerts_returns_over_limit_objective(self):
        Objectif.objects.create(
            type='depense',
            montant=Decimal('50.00'),
            periode='mensuel',
            label='Budget test',
        )
        Transaction.objects.create(
            type='depense',
            montant=Decimal('80.00'),
            label='Depense test',
            entreprise=self.ent,
            user=self.admin,
        )
        self._auth(self.admin)
        response = self.client.get('/api/budget/alerts/?seuil=70')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data['count'], 1)
