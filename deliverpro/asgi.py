import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

from api.routing import websocket_urlpatterns
from .jwt_ws_middleware import JWTAuthMiddlewareStack


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'deliverpro.settings')


application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': JWTAuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
