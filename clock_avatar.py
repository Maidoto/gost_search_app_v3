from __future__ import annotations

import asyncio
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PIL import Image, ImageDraw, ImageFont
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.photos import DeletePhotosRequest, UploadProfilePhotoRequest
from telethon.tl.types import InputPhoto


PROJECT_DIR = Path(__file__).resolve().parent
ENV_FILE = PROJECT_DIR / ".env"
STATE_FILE = PROJECT_DIR / "state.json"
OUTPUT_FILE = PROJECT_DIR / "clock-avatar.jpg"
SESSION_FILE = PROJECT_DIR / "telegram_clock_avatar"
MIN_UPDATE_SECONDS = 60


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    phone: str | None
    session_string: str | None
    timezone: tzinfo
    update_seconds: int
    delete_previous_script_photos: bool
    show_date: bool
    date_format: str


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


def read_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def read_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer, got: {value}") from exc


def parse_utc_offset(value: str) -> timezone:
    value = value.strip()
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":":
        raise ValueError("UTC offset must look like +05:00 or -04:30.")

    sign = 1 if value[0] == "+" else -1
    hours = int(value[1:3])
    minutes = int(value[4:6])

    if hours > 23 or minutes > 59:
        raise ValueError("UTC offset is out of range.")

    return timezone(sign * timedelta(hours=hours, minutes=minutes), name=f"UTC{value}")


def load_timezone(timezone_name: str) -> tzinfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        offset = os.getenv("UTC_OFFSET", "").strip()
        if not offset and timezone_name == "Asia/Tashkent":
            offset = "+05:00"

        if offset:
            try:
                return parse_utc_offset(offset)
            except ValueError as exc:
                raise SystemExit(f"Invalid UTC_OFFSET: {offset}") from exc

        raise SystemExit(
            f"Unknown TIMEZONE: {timezone_name}. Install tzdata or set UTC_OFFSET in .env."
        )


def load_config() -> Config:
    load_dotenv(ENV_FILE)

    api_id_raw = os.getenv("API_ID", "").strip()
    api_hash = os.getenv("API_HASH", "").strip()

    if not api_id_raw or api_id_raw == "123456":
        raise SystemExit("Set API_ID in .env first.")
    if not api_hash or api_hash == "put_your_api_hash_here":
        raise SystemExit("Set API_HASH in .env first.")

    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise SystemExit("API_ID must be a number.") from exc

    timezone_name = os.getenv("TIMEZONE", "Asia/Tashkent").strip() or "Asia/Tashkent"
    timezone_value = load_timezone(timezone_name)

    update_seconds = read_int("UPDATE_SECONDS", MIN_UPDATE_SECONDS)
    if update_seconds < MIN_UPDATE_SECONDS:
        print(
            f"UPDATE_SECONDS={update_seconds} is too frequent for Telegram; "
            f"using {MIN_UPDATE_SECONDS}.",
            flush=True,
        )
        update_seconds = MIN_UPDATE_SECONDS

    phone = os.getenv("PHONE", "").strip() or None
    session_string = os.getenv("TELETHON_SESSION_STRING", "").strip() or None

    return Config(
        api_id=api_id,
        api_hash=api_hash,
        phone=phone,
        session_string=session_string,
        timezone=timezone_value,
        update_seconds=update_seconds,
        delete_previous_script_photos=read_bool("DELETE_PREVIOUS_SCRIPT_PHOTOS", True),
        show_date=read_bool("SHOW_DATE", True),
        date_format=os.getenv("DATE_FORMAT", "%d.%m.%Y"),
    )


def font_candidates() -> list[Path | str]:
    return [
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        "arial.ttf",
        "DejaVuSans.ttf",
    ]


def get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in font_candidates():
        try:
            return ImageFont.truetype(str(candidate), size)
        except OSError:
            continue
    return ImageFont.load_default()


def point_on_circle(cx: int, cy: int, radius: int, degrees: float) -> tuple[float, float]:
    radians = math.radians(degrees)
    return cx + math.cos(radians) * radius, cy + math.sin(radians) * radius


def draw_hand(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    length: int,
    angle_degrees: float,
    width: int,
    fill: str,
) -> None:
    x, y = point_on_circle(center[0], center[1], length, angle_degrees)
    draw.line([center, (x, y)], fill=fill, width=width)


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: str,
) -> None:
    try:
        draw.text(xy, text, font=font, fill=fill, anchor="mm")
    except TypeError:
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        width = right - left
        height = bottom - top
        draw.text((xy[0] - width / 2, xy[1] - height / 2), text, font=font, fill=fill)


def make_clock_avatar(config: Config, output_file: Path = OUTPUT_FILE) -> Path:
    scale = 3
    size = 512 * scale
    center = (256 * scale, 232 * scale)
    radius = 172 * scale

    now = datetime.now(config.timezone)
    image = Image.new("RGB", (size, size), "#0b1020")
    draw = ImageDraw.Draw(image)

    outer = [
        center[0] - 226 * scale,
        center[1] - 226 * scale,
        center[0] + 226 * scale,
        center[1] + 226 * scale,
    ]
    draw.ellipse(outer, fill="#111827", outline="#334155", width=4 * scale)

    face = [
        center[0] - radius,
        center[1] - radius,
        center[0] + radius,
        center[1] + radius,
    ]
    draw.ellipse(face, fill="#0f172a", outline="#475569", width=3 * scale)

    for tick in range(60):
        angle = tick * 6 - 90
        is_hour = tick % 5 == 0
        outer_radius = radius - 16 * scale
        inner_radius = radius - (38 if is_hour else 26) * scale
        width = 5 * scale if is_hour else 2 * scale
        color = "#e5e7eb" if is_hour else "#64748b"
        x1, y1 = point_on_circle(center[0], center[1], inner_radius, angle)
        x2, y2 = point_on_circle(center[0], center[1], outer_radius, angle)
        draw.line([(x1, y1), (x2, y2)], fill=color, width=width)

    minute_angle = now.minute * 6 + now.second * 0.1 - 90
    hour_angle = ((now.hour % 12) + now.minute / 60) * 30 - 90

    draw_hand(draw, center, 88 * scale, hour_angle, 12 * scale, "#f8fafc")
    draw_hand(draw, center, 130 * scale, minute_angle, 8 * scale, "#38bdf8")
    draw.ellipse(
        [
            center[0] - 12 * scale,
            center[1] - 12 * scale,
            center[0] + 12 * scale,
            center[1] + 12 * scale,
        ],
        fill="#38bdf8",
    )

    time_text = now.strftime("%H:%M")
    draw_centered_text(draw, (256 * scale, 407 * scale), time_text, get_font(68 * scale), "#ffffff")

    if config.show_date:
        date_text = now.strftime(config.date_format)
        draw_centered_text(draw, (256 * scale, 456 * scale), date_text, get_font(25 * scale), "#94a3b8")

    image = image.resize((512, 512), Image.Resampling.LANCZOS)
    image.save(output_file, "JPEG", quality=95, optimize=True)
    return output_file


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def input_photo_from_state(state: dict[str, Any]) -> InputPhoto | None:
    photo = state.get("last_script_photo")
    if not isinstance(photo, dict):
        return None

    try:
        return InputPhoto(
            id=int(photo["id"]),
            access_hash=int(photo["access_hash"]),
            file_reference=bytes.fromhex(photo["file_reference"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def photo_to_state(photo: Any, key: str) -> dict[str, Any] | None:
    if not all(hasattr(photo, attr) for attr in ("id", "access_hash", "file_reference")):
        return None

    return {
        "last_key": key,
        "last_script_photo": {
            "id": str(photo.id),
            "access_hash": str(photo.access_hash),
            "file_reference": bytes(photo.file_reference).hex(),
        },
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def extract_uploaded_photo(upload_result: Any) -> Any | None:
    photo = getattr(upload_result, "photo", None)
    if photo is not None:
        return photo
    if hasattr(upload_result, "id"):
        return upload_result
    return None


async def delete_previous_photo(client: TelegramClient, state: dict[str, Any]) -> None:
    input_photo = input_photo_from_state(state)
    if input_photo is None:
        return

    try:
        await client(DeletePhotosRequest(id=[input_photo]))
        print("Deleted previous script photo.", flush=True)
    except Exception as exc:
        print(f"Could not delete previous script photo: {exc}", flush=True)


async def upload_avatar(client: TelegramClient, config: Config, key: str, state: dict[str, Any]) -> dict[str, Any]:
    path = make_clock_avatar(config)
    uploaded_file = await client.upload_file(str(path))
    result = await client(UploadProfilePhotoRequest(file=uploaded_file))

    if config.delete_previous_script_photos:
        await delete_previous_photo(client, state)

    uploaded_photo = extract_uploaded_photo(result)
    next_state = photo_to_state(uploaded_photo, key)
    if next_state is None:
        next_state = {"last_key": key, "updated_at": datetime.now().isoformat(timespec="seconds")}

    save_state(next_state)
    print(f"Avatar updated: {key}", flush=True)
    return next_state


async def run_once(config: Config) -> None:
    state = load_state()
    key = datetime.now(config.timezone).strftime("%Y-%m-%d %H:%M")

    async with create_client(config) as client:
        await start_client(client, config)
        await upload_avatar(client, config, key, state)


async def run_forever(config: Config) -> None:
    state = load_state()

    async with create_client(config) as client:
        await start_client(client, config)
        print("Started. Press Ctrl+C to stop.", flush=True)

        while True:
            key = datetime.now(config.timezone).strftime("%Y-%m-%d %H:%M")

            if state.get("last_key") != key:
                try:
                    state = await upload_avatar(client, config, key, state)
                except FloodWaitError as exc:
                    wait_seconds = int(exc.seconds) + 5
                    print(f"Telegram FloodWait: sleeping {wait_seconds} seconds.", flush=True)
                    await asyncio.sleep(wait_seconds)
                    continue

            await asyncio.sleep(config.update_seconds)


def create_client(config: Config) -> TelegramClient:
    session = StringSession(config.session_string) if config.session_string else str(SESSION_FILE)
    return TelegramClient(session, config.api_id, config.api_hash)


async def start_client(client: TelegramClient, config: Config) -> None:
    if config.phone:
        await client.start(phone=config.phone)
        return

    await client.start(phone=lambda: input("Phone number (+998...): ").strip())


async def print_session_string(config: Config) -> None:
    client = TelegramClient(StringSession(), config.api_id, config.api_hash)
    async with client:
        await start_client(client, config)
        session = client.session.save()
        print("\nCopy this value to Render Environment Variables:\n", flush=True)
        print(f"TELETHON_SESSION_STRING={session}", flush=True)


def main() -> None:
    preview = "--preview" in sys.argv
    once = "--once" in sys.argv
    session_string = "--session-string" in sys.argv

    config = load_config()

    if preview:
        path = make_clock_avatar(config)
        print(f"Preview saved: {path}", flush=True)
        return

    if once:
        asyncio.run(run_once(config))
        return

    if session_string:
        asyncio.run(print_session_string(config))
        return

    asyncio.run(run_forever(config))


if __name__ == "__main__":
    main()
