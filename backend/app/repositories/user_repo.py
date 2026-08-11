
from app.models import User
from app.repositories.base import UserScopedRepository


class UserRepository(UserScopedRepository[User]):
    model = User
    user_id_field = "id"
