import re
import vk_api
import redis
from vk_api.longpoll import VkLongPoll, VkEventType

# Конфигурация
VK_TOKEN = "vk1.a.N7R1ZzqehaEqsQrCTop1_0393i_IMXb1d97egeL-hknSFeKE5t7SrQ6nRol9C6DAQIXZv8tfzN_LJ0CpKFLzfNo5pHiuFaLtaGZVaqp7jrw7Ge44hOPOtQIOu0XAInESC50z7idvWh9cVRojXS6fUNDNgSGr4qrPFnHxSOH1JuLuNdaoSW2efZeDyWdab1D_cJr7-Ode4QTp8R_F9cxBXQ"
GROUP_ID = 230001293  # Укажите ID вашего сообщества
MANAGER_IDS = [321555079]
REDIS_HOST = "redis"
REDIS_PORT = 6379
SESSION_TTL = 3600  # 1 час

vk_session = vk_api.VkApi(token=VK_TOKEN)
longpoll = VkLongPoll(vk_session)
vk = vk_session.get_api()

r = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

# Валидация данных
def validate_name(name):
    pattern = r"^[А-Яа-яЁёA-Za-z-]{2,}\s[А-Яа-яЁёA-Za-z-]{2,}(\s[А-Яа-яЁёA-Za-z-]{2,})?$"
    return re.match(pattern, name)

def validate_phone(phone):
    clean_phone = re.sub(r"\D", "", phone)
    return clean_phone.startswith(("7", "8")) and len(clean_phone) == 11

def validate_city(city):
    pattern = r"^[А-Яа-яЁёA-Za-z\s-]{2,}$"
    return re.match(pattern, city)

# Отправка сообщений
def send_message(user_id, message):
    vk.messages.send(user_id=user_id, message=message, random_id=0)

# Очистка просроченных сессий
def clear_expired_sessions():
    for key in r.keys("user:*"):
        if r.ttl(key) == -1:
            r.delete(key)

def start_bot():
    for event in longpoll.listen():

        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
            user_id = event.user_id
            key = f"user:{user_id}"
            stage = r.hget(key, "stage")
            r.expire(key, SESSION_TTL)

            if not stage:
                r.hset(key, "stage", "wait_for_consent")
                stage = "wait_for_consent"

            text = event.text.strip().lower()

            if stage == "wait_for_consent":
                if text == "да":
                    send_message(user_id, "Отлично! Напишите, пожалуйста, ваш вопрос менеджеру:")
                    r.hset(key, "stage", "ask_question")
                else:
                    send_message(user_id, "Привет! 😊 Это бот нашего курса Рекрутер от Р до Р — твоя новая удалённая профессия. Чтобы оставить заявку, напишите слово — ДА, и наш менеджер свяжется с вами!")

            elif stage == "ask_question":
                r.hset(key, "question", event.text)
                send_message(user_id, "Введите ваше ФИО:")
                r.hset(key, "stage", "get_name")

            elif stage == "get_name":
                if validate_name(event.text):
                    r.hset(key, "name", event.text)
                    send_message(user_id, "Введите номер телефона:")
                    r.hset(key, "stage", "get_phone")
                else:
                    send_message(user_id, "Пожалуйста, введите корректное ФИО.")

            elif stage == "get_phone":
                if validate_phone(event.text):
                    r.hset(key, "phone", event.text)
                    send_message(user_id, "Введите город:")
                    r.hset(key, "stage", "get_city")
                else:
                    send_message(user_id, "Пожалуйста, введите корректный номер телефона.")

            elif stage == "get_city":
                if validate_city(event.text):
                    r.hset(key, "city", event.text)
                    name = r.hget(key, "name")
                    phone = r.hget(key, "phone")
                    city = r.hget(key, "city")
                    question = r.hget(key, "question")

                    summary = (
                        f"Новая заявка от пользователя https://vk.ru/id{user_id}\n"
                        f"ФИО: {name}\n"
                        f"Телефон: {phone}\n"
                        f"Город: {city}\n"
                        f"Вопрос: {question}"
                    )
                    for manager_id in MANAGER_IDS:
                        send_message(manager_id, summary)
                    send_message(user_id, "Спасибо! Наш менеджер скоро свяжется с вами!")
                    r.delete(key)
                else:
                    send_message(user_id, "Пожалуйста, введите корректное название города.")

        # elif event.type == VkEventType.GROUP_JOIN:
        #     user_id = event.user_id
        #     key = f"user:{user_id}"
        #     send_message(user_id, "Привет! 😊 это бот нашего курса Рекрутер от Р до Р, твоя новая удаленная профессия. Чтобы оставить заявку, напишите слово — ДА, и наш менеджер свяжется с вами!")
        #     r.hset(key, "stage", "wait_for_consent")
        #     r.expire(key, SESSION_TTL)

if __name__ == "__main__":
    start_bot()
