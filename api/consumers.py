from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import EntrepriseAccess


class UpdatesConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return

        self._groups = ['updates_all', f'updates_user_{user.id}']
        if user.role == 'livreur':
            self._groups.append(f'updates_livreur_{user.id}')
        if user.role == 'admin':
            ent_ids = await self._get_scope_ids(user.id)
            for ent_id in ent_ids:
                self._groups.append(f'updates_ent_{ent_id}')

        for group_name in self._groups:
            await self.channel_layer.group_add(group_name, self.channel_name)

        await self.accept()
        await self.send_json({'event': 'ws.connected', 'payload': {'user_id': user.id}})

    async def disconnect(self, close_code):
        for group_name in getattr(self, '_groups', []):
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def broadcast_message(self, event):
        await self.send_json({
            'event': event.get('event'),
            'payload': event.get('payload', {}),
        })

    @database_sync_to_async
    def _get_scope_ids(self, user_id):
        return list(
            EntrepriseAccess.objects.filter(user_id=user_id).values_list('entreprise_id', flat=True)
        )
