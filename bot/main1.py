import re
import redis
from fastapi import FastAPI, Request
from pydantic import BaseModel
import uvicorn
import vk_api
import httpx
import os

VK_TOKEN = os.getenv('VK_TOKEN')
VK_SECRET = os.getenv('VK_SECRET')
VK_CONFIRMATION = os.getenv('VK_CONFIRMATION')
MANAGER_ID = os.getenv('MANAGER_ID')
REDIS_HOST = "redis"
REDIS_PORT = 6379
SESSION_TTL = 3600

vk_session = vk_api.VkApi(token=VK_TOKEN)
vk = vk_session.get_api()
r = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

app = FastAPI()

class VKEvent(BaseModel):
    type: str
    group_id: int
    event_id: str
    secret: str = None
    object: dict

# Валидация

def validate_name(name):
    pattern = r"^[А-Яа-яЁёA-Za-z-]{2,}\s[А-Яа-яЁёA-Za-z-]{2,}(\s[А-Яа-яЁёA-Za-z-]{2,})?$"
    return re.match(pattern, name)

def validate_phone(phone):
    clean_phone = re.sub(r"\D", "", phone)
    return clean_phone.startswith(("7", "8")) and len(clean_phone) == 11

def validate_city(city):
    pattern = r"^[А-Яа-яЁёA-Za-z\s-]{2,}$"
    return re.match(pattern, city)

def send_message(user_id, message):
    vk.messages.send(user_id=user_id, message=message, random_id=0)

def clear_expired_sessions():
    for key in r.keys("user:*"):
        if r.ttl(key) == -1:
            r.delete(key)

@app.post("/callback")
async def callback(event: VKEvent):
    if event.secret and event.secret != VK_SECRET:
        return "invalid secret"

    if event.type == "confirmation":
        return VK_CONFIRMATION

    if event.type == "message_new":
        user_id = event.object["message"]["from_id"]
        message_text = event.object["message"]["text"].strip().lower()
        key = f"user:{user_id}"
        stage = r.hget(key, "stage")
        await r.expire(key, SESSION_TTL)

        if not stage:
            send_message(user_id, "Привет! 😊 Это бот нашего курса Рекрутер от Р до Р — твоя новая удалённая профессия. Чтобы оставить заявку, напишите слово — ДА, и наш менеджер свяжется с вами!")
            await r.hset(key, "stage", "wait_for_consent")
            return "ok"

        if stage == "wait_for_consent":
            if message_text == "да":
                send_message(user_id, "Отлично! Напишите, пожалуйста, ваш вопрос менеджеру:")
                await r.hset(key, "stage", "ask_question")
            else:
                send_message(user_id, "Пожалуйста, напишите ДА, чтобы оставить заявку.")

        elif stage == "ask_question":
            await r.hset(key, "question", event.object["message"]["text"])
            send_message(user_id, "Введите ваше ФИО:")
            await r.hset(key, "stage", "get_name")

        elif stage == "get_name":
            if validate_name(event.object["message"]["text"]):
                await r.hset(key, "name", event.object["message"]["text"])
                send_message(user_id, "Введите номер телефона:")
                await r.hset(key, "stage", "get_phone")
            else:
                send_message(user_id, "Пожалуйста, введите корректное ФИО.")

        elif stage == "get_phone":
            if validate_phone(event.object["message"]["text"]):
                await r.hset(key, "phone", event.object["message"]["text"])
                send_message(user_id, "Введите город:")
                await r.hset(key, "stage", "get_city")
            else:
                send_message(user_id, "Пожалуйста, введите корректный номер телефона.")

        elif stage == "get_city":
            if validate_city(event.object["message"]["text"]):
                await r.hset(key, "city", event.object["message"]["text"])
                name = r.hget(key, "name")
                phone = r.hget(key, "phone")
                city = r.hget(key, "city")
                question = r.hget(key, "question")

                summary = (
                    f"Новая заявка от пользователя {user_id}\n"
                    f"ФИО: {name}\n"
                    f"Телефон: {phone}\n"
                    f"Город: {city}\n"
                    f"Вопрос: {question}"
                )
                send_message(MANAGER_ID, summary)
                send_message(user_id, "Спасибо! Наш менеджер скоро свяжется с вами!")
                await r.delete(key)
            else:
                send_message(user_id, "Пожалуйста, введите корректное название города.")

    elif event.type == "group_join":
        user_id = event.object["user_id"]
        send_message(user_id, "Привет! 😊 Это бот нашего курса Рекрутер от Р до Р — твоя новая удалённая профессия. Чтобы оставить заявку, напишите слово — ДА, и наш менеджер свяжется с вами!")
        await r.hset(f"user:{user_id}", "stage", "wait_for_consent")
        await r.expire(f"user:{user_id}", SESSION_TTL)

    return "ok"