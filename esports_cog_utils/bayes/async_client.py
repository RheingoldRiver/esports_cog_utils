import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Literal, Optional, Union

import backoff
from aiofiles import open as aopen
from aiohttp import ClientResponseError, ClientSession

from .errors import BayesBadAPIKeyException, BayesBadRequestException, BayesRateLimitException, \
    BayesUnexpectedResponseException
from .shared_types import AssetType, BaseBayesClient, Game, GetGamesResponse, INFINITY, RPGId, Service, Tag


class AsyncBayesClient(BaseBayesClient):
    async def _save_login(self):
        os.makedirs(os.path.dirname(self.SAVE_FILE), exist_ok=True)
        async with aopen(self.SAVE_FILE, 'w+') as f:
            await f.write(json.dumps({
                'accessToken': self.access_token,
                'refreshToken': self.refresh_token,
                'expiresIn': self.expires.timestamp()
            }))

    async def _ensure_login(self, force_relogin: bool = False) -> None:
        """Ensure that the access_token is recent and valid"""
        if force_relogin:
            try:
                data = await self._do_api_call('POST', Service.LOGIN,
                                               {'username': self.username, 'password': self.password},
                                               ensure_keys=['accessToken', 'refreshToken', 'expiresIn'])
            except ClientResponseError as e:
                if e.status == 500:
                    raise BayesBadAPIKeyException()
                raise
            self.expires = datetime.now() + timedelta(seconds=data['expiresIn'])
        elif self.access_token is None:
            try:
                async with aopen(self.SAVE_FILE) as f:
                    data = json.loads(await f.read())
            except FileNotFoundError:
                return await self._ensure_login(force_relogin=True)
            self.expires = datetime.fromtimestamp(data['expiresIn'])
            if self.expires <= datetime.now():
                return await self._ensure_login(force_relogin=False)
        elif self.expires <= datetime.now():
            try:
                data = await self._do_api_call('POST', Service.REFRESH,
                                               {'refreshToken': self.refresh_token},
                                               ensure_keys=['accessToken', 'refreshToken', 'expiresIn'])
                self.expires = datetime.now() + timedelta(seconds=data['expiresIn'])
            except ClientResponseError as cre:
                if cre.status == 500:
                    return await self._ensure_login(force_relogin=True)
                raise
        else:
            return

        self.access_token = data['accessToken']
        self.refresh_token = data['refreshToken']
        await self._save_login()

    @backoff.on_exception(backoff.expo, BayesRateLimitException, logger=None)
    async def _do_api_call(self, method: Literal['GET', 'POST'], service: str,
                           data: Dict[str, Any] = None, *, allow_retry: bool = True,
                           ensure_keys: Optional[Iterable[str]] = None):
        """Make a single API call to emh-api.bayesesports.com"""
        if data is None:
            data = {}
        if ensure_keys is None:
            ensure_keys = []

        if self.session is None:
            self.session = ClientSession()
        if method == "GET":
            async with self.session.get(self.ENDPOINT + service, headers=await self._get_headers(),
                                        params=data) as resp:
                if resp.status == 401 and allow_retry:
                    await self._ensure_login(force_relogin=True)
                    return await self._do_api_call(method, service, data, allow_retry=False, ensure_keys=ensure_keys)
                elif resp.status == 429:
                    raise BayesRateLimitException()
                resp.raise_for_status()
                data = await resp.json()
        elif method == "POST":
            async with self.session.post(self.ENDPOINT + service, json=data) as resp:
                resp.raise_for_status()
                data = await resp.json()
        else:
            raise ValueError("HTTP Method must be GET or POST.")
        if not all(key in data for key in ensure_keys):
            raise BayesUnexpectedResponseException(service, data)
        return data

    async def _get_headers(self) -> Dict[str, str]:
        """Return headers for a GET request to the API"""
        await self._ensure_login()
        return {'Authorization': f'Bearer {self.access_token}'}

    async def get_tags(self) -> List[Tag]:
        """Return a list of tags that can be used to request games"""
        return self.SPECIAL_TAGS + await self._do_api_call('GET', Service.TAGS)

    async def get_games(self, *, page: Optional[int] = None, page_size: Optional[int] = None,
                        from_timestamp: Optional[Union[datetime, str]] = None,
                        to_timestamp: Optional[Union[datetime, str]] = None,
                        tags: Optional[Iterable[Tag]] = None) \
            -> GetGamesResponse:
        """Make an API query to the api/v1/games endpoint"""
        if isinstance(from_timestamp, datetime):
            from_timestamp = from_timestamp.isoformat()
        if isinstance(to_timestamp, datetime):
            to_timestamp = to_timestamp.isoformat()
        tags = ','.join(tags) if tags is not None else None

        params = {'page': page, 'size': page_size, 'from_timestamp': from_timestamp,
                  'to_timestamp': to_timestamp, 'tags': tags}
        params = {k: v for k, v in params.items() if v is not None}
        return await self._do_api_call('GET', Service.GAMES, params, ensure_keys=GetGamesResponse.__annotations__)

    async def get_all_games(self, *, tag: Optional[Tag] = None, tags: Optional[Iterable[Tag]] = None,
                            from_timestamp: Optional[Union[datetime, str]] = None,
                            to_timestamp: Optional[Union[datetime, str]] = None) \
            -> List[Game]:
        """Get all games with the given filters"""
        tags, only_null = self._validate_tags(tag, tags)
        data = await self.get_games(tags=tags, page_size=INFINITY,
                                    from_timestamp=from_timestamp,
                                    to_timestamp=to_timestamp)
        if data['count'] >= INFINITY:
            page = 1
            while len(data['games']) < data['count']:
                newpage = await self.get_games(tags=tags, page=page, page_size=INFINITY,
                                               from_timestamp=from_timestamp,
                                               to_timestamp=to_timestamp)
                data['games'].extend(newpage['games'])
                if not newpage['games']:
                    break
                page += 1
        return [self._clean_game(game) for game in data['games'] if not (game['tags'] and only_null)]

    async def get_game(self, rpgid: RPGId) -> Game:
        """Get a game by its ID"""
        try:
            game = await self._do_api_call('GET', Service.GAME.format(rpgid=rpgid))
        except ClientResponseError as e:
            if e.status == 404:
                raise BayesBadRequestException(f'Invalid Game ID: {rpgid}')
            raise
        return self._clean_game(game)

    async def get_asset(self, rpgid: RPGId, asset: AssetType) -> bytes:
        """Get the bytes for an asset"""
        game = await self.get_game(rpgid)
        if asset not in game['assets']:
            raise BayesBadRequestException(f'Invalid asset type for game with ID {rpgid}: {asset}')
        data = await self._do_api_call('GET', Service.ASSET.format(rpgid=rpgid), {'type': asset}, ensure_keys=['url'])
        async with self.session.get(data['url']) as resp:
            return await resp.read()
