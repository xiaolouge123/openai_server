import os
import json
import asyncio
from pydantic import BaseModel
from loguru import logger
import aiohttp
from typing import List, Union, Optional, AsyncGenerator
from aiohttp_sse_client import client as sse_client

from utils import SingletonClientSession
from exceptions import OpenaiApiException
from helper import Handlers, key, record_tokens, proxy, retry

ENABLE_PROXY = os.environ.get("ENABLE_PROXY", True)


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: List[Message]
    temperature: float = 1
    top_p: float = 1
    n: int = 1
    max_tokens: int = 256
    stop: Union[str, List[str]] = None
    presence_penalty: float = 0
    frequency_penalty: float = 0
    stream: bool = False

    def get_prompt_text(self):
        # TODO just approx calculation
        texts = []
        for msg in self.messages:
            texts.append(msg.content)
        return " ".join(texts)

    def __str__(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False)


class Choice(BaseModel):
    index: int
    message: Message
    finish_reason: str


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    id: str
    object: str
    created: int
    model: str
    choices: List[Choice]
    usage: Usage

    def get_generation_text(self):
        return self.choices[0].message.content

    def __str__(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False)


class Chunk(BaseModel):
    index: int
    delta: dict
    finish_reason: Optional[str]


class ChatResponseChunk(BaseModel):
    id: str
    object: str
    created: int
    model: str
    choices: List[Chunk]


@proxy(enable=ENABLE_PROXY)
@key(Handlers.get_key_handler)
async def get_models(**kwargs):
    session = await SingletonClientSession.get_session()
    async with session.get(
        "https://api.openai.com/v1/models",
        proxy=kwargs.pop("proxy"),
        headers=kwargs.pop("headers"),
    ) as resp:
        models = await resp.json()
        model_names = []
        for model in models["data"]:
            model_names.append(model["id"])
        return {"models": sorted(model_names)}


@proxy(enable=ENABLE_PROXY)
@key(Handlers.get_key_handler)
@record_tokens(Handlers.get_record_handler)
async def get_chat_completion(chat_request: ChatRequest, **kwargs) -> ChatResponse:
    timeout = aiohttp.ClientTimeout(total=60)
    session = await SingletonClientSession.get_session()
    # logger.info(chat_request.model_dump(mode='json'))
    try:
        async with session.post(
            "https://api.openai.com/v1/chat/completions",
            proxy=kwargs.pop("proxy"),
            headers=kwargs.pop("headers"),
            json=chat_request.model_dump(mode="json"),
            timeout=timeout,
        ) as resp:
            if resp.status != 200:
                # raise OpenaiApiException(msg=resp.text, status_code=resp.status)
                print(resp.status, resp.text)
            completion = await resp.json()
            # logger.info(completion)
            return ChatResponse(**completion)
    except Exception as e:
        logger.warning(e)


async def get_chat_completion_stream(
    chat_request: ChatRequest, **kwargs
) -> AsyncGenerator[ChatResponseChunk, None]:
    session = await SingletonClientSession.get_session()
    async with sse_client.EventSource(
        "https://api.openai.com/v1/chat/completions",
        session=session,
        option={"method": "POST"},
        proxy=kwargs.pop("proxy"),
        headers=kwargs.pop("headers"),
        json=chat_request.model_dump(mode="json"),
    ) as event_source:
        try:
            async for event in event_source:
                if event.data != "[DONE]":
                    yield ChatResponseChunk(**json.loads(event.data))
                else:
                    break
        except ConnectionError:
            pass


async def test_stream(chat_request):
    async for chunk in get_chat_completion_stream(chat_request):
        print(chunk)


async def test_batch(chat_request):
    resp = await get_chat_completion(chat_request)
    print(resp)


# chat_req = ChatRequest(
#     model="gpt-3.5-turbo",
#     messages=[
#         {"role": "system", "content": "You are a helpful assistant."},
#         {"role": "user", "content": "Hello!"},
#     ],
# )

# chat_req_stream = ChatRequest(
#     model="gpt-3.5-turbo",
#     messages=[
#         {"role": "system", "content": "You are a helpful assistant."},
#         {"role": "user", "content": "Hello!"},
#     ],
#     stream=True,
# )


# loop = asyncio.get_event_loop()
# loop.run_until_complete(get_models())
# # loop.run_until_complete(get_chat_completion(chat_req))
# # loop.run_until_complete(get_chat_completion_stream(chat_req_stream))
# loop.run_until_complete(test_stream(chat_req_stream))
# loop.run_until_complete(test_batch(chat_req))
# loop.run_until_complete(SingletonClientSession.close_session())
# loop.close()
# asyncio.run(get_chat_completion(chat_req))
