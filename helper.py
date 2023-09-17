import os
import time
import aiomysql
import asyncio
from collections import OrderedDict
from functools import wraps
import tiktoken
from loguru import logger

from exceptions import NoValidKey

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", 3306)
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "123456")
DB_NAME = os.environ.get("DB_NAME", "OpenAIUsage")


def get_time():
    return int(time.time())


class Handlers:
    _key_handler = None
    _record_handler = None
    pool = None

    @classmethod
    async def get_key_handler(cls):
        if cls.pool is None:
            cls.pool = await aiomysql.create_pool(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                db=DB_NAME,
            )
            logger.info("Aiomysql connection pool is ready from key handler")
        if cls._key_handler is None:
            cls._key_handler = KeyPoolHandler(pool=cls.pool)
            await cls._key_handler.async_init()
            # await asyncio.create_task(cls._key_handler._keypool_update()) # TODO blocking
        return cls._key_handler

    @classmethod
    async def get_record_handler(cls):
        if cls.pool is None:
            cls.pool = await aiomysql.create_pool(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                db=DB_NAME,
            )
            logger.info("Aiomysql connection pool is ready from record handler")
        if cls._record_handler is None:
            cls._record_handler = RecordHandler(pool=cls.pool)
        return cls._record_handler


class RecordHandler:
    def __init__(self, pool):
        self.pool = pool

    async def record_tokens(
        self,
        api_key,
        model_name,
        request_body,
        prompt_token_num,
        generation,
        generation_token_num,
    ):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "INSERT INTO RequestRecords SET apiKey = %s, modelName = %s, request_body = %s, prompt_token_count = %s, generation_response = %s, generation_token_count = %s",
                    (
                        api_key,
                        model_name,
                        request_body,
                        prompt_token_num,
                        generation,
                        generation_token_num,
                    ),
                )
                await conn.commit()


class KeyPoolHandler:
    def __init__(self, pool):
        self.pool = pool
        self.keypool = None
        self.call_limit = 3  # 3 requests per minute
        self.call_interval = 60  # 60 seconds
        self.last_key_index = 0

    async def async_init(self):
        self.keypool = await self.get_all_keys()

    async def get_all_keys(self):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT apiKey, comment, available, usageLimit FROM APIKeys"
                )
                result = await cursor.fetchall()
                keys_dict = OrderedDict()
                for row in result:
                    keys_dict[row[0]] = {
                        "comment": row[1],
                        "available": row[2],
                        "usage_count": 0,
                        "usage_limit": row[3],
                        "in_last_min": get_time(),
                    }
                logger.info("KeyPool Initializing")
                return keys_dict

    def get_key(self):
        keys = list(self.keypool.keys())
        start_index = self.last_key_index
        cnt = 0
        while True:
            api_key = keys[self.last_key_index]
            key_data = self.keypool[api_key]
            current_time = get_time()
            if self._check_key(key_data, current_time=current_time):
                self.last_key_index = start_index
                return api_key
            else:
                self.last_key_index = (self.last_key_index + 1) % len(keys)
                cnt += 1
                if cnt == len(keys):
                    raise NoValidKey(
                        f"To many loop, No available key in {len(keys)} key pool"
                    )

    def _check_key(self, key_info, **kwargs):
        if key_info["available"] is False:
            return False
        current_time = kwargs.get("current_time", get_time())
        if current_time - key_info["in_last_min"] <= self.call_interval:
            if key_info["usage_count"] >= key_info["usage_limit"]:
                return False
            else:
                key_info["usage_count"] += 1
                return True
        else:
            key_info["usage_count"] = 1
            key_info["in_last_min"] = current_time
            return True

    async def set_key_status(self, api_key, available, comment):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "UPDATE APIKeys SET available = %s, comment = %s WHERE apiKey = %s",
                    (available, comment, api_key),
                )
                await conn.commit()

                if api_key in self.keypool:
                    self.keypool[api_key]["available"] = available
                    self.keypool[api_key]["comment"] = comment

                logger.info("Key status updated")

    async def _keypool_update(self, internal=300):
        while True:
            await asyncio.sleep(internal)
            self.keypool = await self.get_all_keys()  # 更新 keypool
            logger.info("KeyPool has been updated")


def count_token(model, text):
    encoding = tiktoken.encoding_for_model(model)
    token_count = len(encoding.encode(text))
    return token_count


def record_tokens(handler_coro):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            handler = await handler_coro()
            req = args[0]
            if isinstance(req, dict):
                model_name = req["model"]
            else:
                model_name = req.model
            api_key = kwargs.pop("apikey", None)
            if api_key is None:
                raise NoValidKey("Got None")
            if isinstance(req, dict):
                prompt_tokens = 1
                response = None
                generation_tokens = 2
            else:
                prompt_tokens = count_token(model_name, req.get_prompt_text())
                response = await func(*args, **kwargs)
                generation_tokens = count_token(
                    model_name, response.get_generation_text()
                )
            await handler.record_tokens(
                api_key,
                model_name,
                str(req),
                prompt_tokens,
                str(response),
                generation_tokens,
            )
            return response

        return wrapper

    return decorator


def key(handler_coro):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            handler = await handler_coro()
            logger.info(handler)
            apikey = handler.get_key()

            headers = {
                "Authorization": "Bearer " + apikey,
                "Content-Type": "application/json",
            }
            kwargs["headers"] = headers
            kwargs["apikey"] = apikey
            response = await func(*args, **kwargs)
            return response

        return wrapper

    return decorator


def proxy(enable=True):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            proxy = os.environ.get("OPENAI_PROXY", "http://127.0.0.1:7890")
            if enable:
                kwargs["proxy"] = proxy
            else:
                kwargs["proxy"] = None
            response = func(*args, **kwargs)
            return response

        return wrapper

    return decorator


@proxy(enable=True)
@key(Handlers.get_key_handler())
@record_tokens(Handlers.get_record_handler())
async def test(*args, **kwargs):
    print("test args", args)
    print("test kwargs", kwargs)


if __name__ == "__main__":
    req = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
        ],
    }
    asyncio.run(test(req))
