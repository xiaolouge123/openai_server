import aiohttp


class SingletonClientSession:
    _session = None

    @classmethod
    async def get_session(cls):
        if cls._session is None:
            cls._session = aiohttp.ClientSession()
        return cls._session

    @classmethod
    async def close_session(cls):
        if cls._session is not None:
            await cls._session.close()
            cls._session = None