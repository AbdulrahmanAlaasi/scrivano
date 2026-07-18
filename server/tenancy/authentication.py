"""Supabase Auth integration.

The SPA signs in against Supabase Auth and sends the resulting access token as
`Authorization: Bearer <jwt>`. We verify it with the project's JWT secret
(HS256, audience "authenticated") and mirror the user locally by their
Supabase subject id.
"""

import jwt
from django.conf import settings
from rest_framework import authentication, exceptions

from .models import User


class SupabaseJWTAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("utf-8")
        if not header.startswith(f"{self.keyword} "):
            return None
        token = header[len(self.keyword) + 1 :].strip()
        if not settings.SUPABASE_JWT_SECRET:
            raise exceptions.AuthenticationFailed("Supabase auth is not configured.")
        try:
            claims = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
            )
        except jwt.PyJWTError as err:
            raise exceptions.AuthenticationFailed(f"Invalid token: {err}") from err

        supabase_id = claims.get("sub")
        if not supabase_id:
            raise exceptions.AuthenticationFailed("Token missing subject.")
        email = claims.get("email", "")
        user, created = User.objects.get_or_create(
            supabase_id=supabase_id,
            defaults={"username": supabase_id, "email": email},
        )
        if not created and email and user.email != email:
            user.email = email
            user.save(update_fields=["email"])
        return (user, claims)

    def authenticate_header(self, request):
        return self.keyword
