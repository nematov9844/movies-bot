from dataclasses import dataclass
from datetime import UTC, datetime

from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
from app.database.models import User
from app.database.repositories.movie_view_repository import MovieViewRepository
from app.database.repositories.referral_repository import ReferralRepository
from app.database.repositories.user_repository import UserRepository
from app.services.premium.premium_service import PremiumService
from app.services.stats.stats_service import increment_new_user, mark_active_user


@dataclass(slots=True)
class UserProfile:
    """Read-only, user-facing view of a user's account, for the Profil screen."""

    telegram_id: int
    full_name: str
    language: str
    premium_active: bool
    premium_expires_at: datetime | None
    movies_watched: int
    referral_count: int


class UserService:
    """Business logic for the ``users`` table.

    Phase 3 only needed the telegram-upsert flow used on every bot update.
    Phase 5 extends this same class with the profile, settings, and referral
    flows the user-facing handlers need — profile assembly reads across
    premium/movie-view/referral repositories, which is business logic that
    belongs here rather than being duplicated in handlers.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = UserRepository(session)
        self._premium_service = PremiumService(session)
        self._movie_view_repo = MovieViewRepository(session)
        self._referral_repo = ReferralRepository(session)

    async def upsert_from_telegram(self, tg_user: TelegramUser) -> User:
        """Insert-or-refresh a user row from an incoming Telegram user object.

        Also feeds Phase 10's live stats counters: a fresh insert bumps
        ``stats:today:new_users``, and every call (new or returning user)
        marks the user active for today's distinct-active-users set —
        this runs on every single bot update, so it's the one place that
        can observe both without extra queries.
        """
        user, is_new = await self._repo.upsert(
            tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            last_seen_at=datetime.now(UTC),
        )
        if is_new:
            await increment_new_user()
        await mark_active_user(user.id)
        return user

    async def get_language(self, user_id: int) -> str:
        """The stored UI language for ``user_id``, defaulting to ``DEFAULT_LANGUAGE``.

        By the time any handler runs, ``UserUpsertMiddleware`` has already
        upserted a row for the acting user, so the ``None`` branch here is
        only a defensive fallback (e.g. looking up some other user_id).
        """
        user = await self._repo.get(user_id)
        return user.language if user is not None else DEFAULT_LANGUAGE

    async def set_language(self, user_id: int, language: str) -> User | None:
        """Update ``users.language``. Raises ``ValueError`` for an unsupported code."""
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {language}")
        return await self._repo.update(user_id, language=language)

    async def get_referral_count(self, user_id: int) -> int:
        """How many users ``user_id`` has successfully referred."""
        return await self._referral_repo.count(referrer_id=user_id)

    async def record_referral(self, referred_id: int, referrer_id: int) -> bool:
        """Record that ``referrer_id`` referred ``referred_id`` into the bot.

        First referral wins: a no-op (returns ``False``, no exception) for
        self-referral, an unknown referrer, or a user who already has a
        ``referrer_id`` set. The ``referrals`` audit row is inserted with
        ``ON CONFLICT DO NOTHING`` on its unique ``referred_id`` column, so
        concurrent duplicate attempts (e.g. the user replaying the deep
        link) converge safely instead of raising — this is expected user
        behavior, not an error.

        On success, both the denormalized ``users.referrer_id`` column and
        the ``referrals`` audit row are updated in this one DB transaction
        (the caller commits at the end of the update, per
        ``DbSessionMiddleware``).
        """
        if referred_id == referrer_id:
            return False

        referred_user = await self._repo.get(referred_id)
        if referred_user is None or referred_user.referrer_id is not None:
            return False

        referrer_user = await self._repo.get(referrer_id)
        if referrer_user is None:
            return False

        inserted = await self._referral_repo.create_if_absent(
            referrer_id=referrer_id, referred_id=referred_id
        )
        if not inserted:
            return False

        referred_user.referrer_id = referrer_id
        await self._session.flush()
        return True

    async def get_profile(self, user_id: int) -> UserProfile | None:
        """Compose the Profil screen's data from across the user's related rows."""
        user = await self._repo.get(user_id)
        if user is None:
            return None

        premium = await self._premium_service.get_active(user_id)
        movies_watched = await self._movie_view_repo.count(user_id=user_id)
        referral_count = await self.get_referral_count(user_id)

        name_parts = [part for part in (user.first_name, user.last_name) if part]
        full_name = " ".join(name_parts) if name_parts else (user.username or str(user.id))

        return UserProfile(
            telegram_id=user.id,
            full_name=full_name,
            language=user.language,
            premium_active=premium is not None,
            premium_expires_at=premium.expires_at if premium is not None else None,
            movies_watched=movies_watched,
            referral_count=referral_count,
        )
