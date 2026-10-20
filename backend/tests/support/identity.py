from auth.models import User
from observability.user_context import set_user_context


def identity_dependency(user: User):
    async def identity():
        actor = user() if callable(user) else user
        set_user_context(actor)
        return actor

    return identity
