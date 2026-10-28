"""Asynchronous local bridge API, based on theOrakle's client."""

from __future__ import annotations

import asyncio
import json
from urllib.parse import quote

import aiohttp


class ApiError(Exception):
    """Bridge request or response failed."""


class BridgeApi:
    def __init__(self, host: str, session: aiohttp.ClientSession):
        self.host = host
        self.session = session
        self.lock = asyncio.Lock()

    async def request(self, method: str, path: str = "", data=None):
        try:
            async with asyncio.timeout(10):
                async with self.session.request(
                    method,
                    f"http://{self.host}/v1{path}",
                    json=data,
                    headers={"Connection": "close"},
                ) as response:
                    response.raise_for_status()
                    body = await response.text()
                    return json.loads(body) if body else None
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise ApiError("Bridge request failed") from err

    async def write(self, method, path, data=None):
        async with self.lock:
            return await self.request(method, path, data)

    async def sequence(self, serial, body=None):
        return await self.write(
            "DELETE" if body is None else "POST",
            f"/zones/{quote(serial, safe='')}/sequence",
            body,
        )
