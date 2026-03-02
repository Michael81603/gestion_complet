from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def broadcast_event(event_name, payload, entreprise_id=None, livreur_id=None):
    """
    Diffuse un événement temps réel sur les groupes websocket.
    """
    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    message = {
        'type': 'broadcast_message',
        'event': event_name,
        'payload': payload,
    }

    async_to_sync(channel_layer.group_send)('updates_all', message)
    if entreprise_id:
        async_to_sync(channel_layer.group_send)(f'updates_ent_{entreprise_id}', message)
    if livreur_id:
        async_to_sync(channel_layer.group_send)(f'updates_livreur_{livreur_id}', message)
