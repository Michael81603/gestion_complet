from urllib.parse import parse_qs

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication


@database_sync_to_async
def get_user_from_token(token):
    auth = JWTAuthentication()
    validated_token = auth.get_validated_token(token)
    return auth.get_user(validated_token)


class JWTAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        scope['user'] = AnonymousUser()

        token = None
        query_string = parse_qs(scope.get('query_string', b'').decode())
        if query_string.get('token'):
            token = query_string['token'][0]
        else:
            headers = dict(scope.get('headers', []))
            auth_header = headers.get(b'authorization', b'').decode()
            if auth_header.lower().startswith('bearer '):
                token = auth_header.split(' ', 1)[1].strip()

        if token:
            try:
                scope['user'] = await get_user_from_token(token)
            except Exception:
                scope['user'] = AnonymousUser()

        return await self.inner(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    return JWTAuthMiddleware(AuthMiddlewareStack(inner))
