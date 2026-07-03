from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import IsAdmin
from app.core.logger import get_logger
from app.services.admin.admin_service import AdminService
from app.services.audit.audit_service import AuditService

router = Router(name="admin_auth")
logger = get_logger(__name__)

MIN_PASSWORD_LENGTH = 8

USAGE_TEXT = (
    "Foydalanish: <code>/setpassword parol</code>\n"
    "Admin panelga kirish uchun parol o'rnatadi. Parol kamida 8 belgidan iborat bo'lishi kerak."
)
TOO_SHORT_TEXT = "❌ Parol juda qisqa. Kamida 8 belgidan iborat bo'lishi kerak."
SUCCESS_TEXT = (
    "✅ Parolingiz muvaffaqiyatli o'rnatildi. Endi admin panelga shu parol bilan kirishingiz mumkin."
)
FAILED_TEXT = "❌ Parolni o'rnatib bo'lmadi: admin huquqingiz faol emas."


@router.message(Command("setpassword"), IsAdmin())
async def cmd_set_password(message: Message, command: CommandObject, session: AsyncSession) -> None:
    """Lets any active admin (owner/admin/moderator) set their own web-panel password."""
    user = message.from_user
    if user is None:
        return

    password = (command.args or "").strip()
    if not password:
        await message.answer(USAGE_TEXT)
        return

    if len(password) < MIN_PASSWORD_LENGTH:
        await message.answer(TOO_SHORT_TEXT)
        return

    admin_service = AdminService(session)
    updated = await admin_service.set_password(user.id, password)
    if not updated:
        await message.answer(FAILED_TEXT)
        return

    admin = await admin_service.get_by_user_id(user.id)
    await AuditService(session).log(
        admin_id=admin.id if admin is not None else None,
        action="set_password",
        entity="admin",
        entity_id=str(user.id),
    )

    await message.answer(SUCCESS_TEXT)
    logger.info("admin_password_set", user_id=user.id)
