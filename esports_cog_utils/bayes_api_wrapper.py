from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Literal, Optional, TypedDict, Union

import backoff
from aiohttp import ClientResponseError, ClientSession

from errors import BadRequestException, BayesBadAPIKeyException, BayesUnexpectedResponseException

GameID = str
AssetType = Literal['GAMH_DETAILS', 'GAMH_SUMMARY', 'ROFL_REPLAY']
Tag = Union[str, Literal['NULL', 'ALL']]


class Game(TypedDict):
    platformGameId: GameID
    name: str
    status: str
    createdAt: str  # ISO-8601 Formatted
    assets: List[AssetType]
    tags: List[Tag]


class GetGamesResponse(TypedDict):
    page: int
    size: int
    count: int
    games: List[Game]


class RateLimitException(Exception):
    pass


class BayesAPIWrapper:
    ENDPOINT = "https://emh-api.bayesesports.com/"
    SPECIAL_TAGS = ['NULL', 'ALL']

    def __init__(self, username: str, password: str, *, session: ClientSession = None):
        self.username = username
        self.password = password

        self.session = session

        self.access_token = None
        self.expires = datetime.min

    async def _ensure_login(self, force_relogin: bool = False) -> None:
        """Ensure that the access_token is recent and valid"""
        if self.access_token is None or force_relogin:
            try:
                data = await self._do_api_call('POST', 'login',
                                               {'username': self.username, 'password': self.password},
                                               ensure_keys=['accessToken', 'expiresIn'])
            except ClientResponseError as e:
                if e.status == 500:
                    raise BayesBadAPIKeyException()
                raise
            self.access_token = data['accessToken']
            self.expires = datetime.now() + timedelta(seconds=data['expiresIn'])

    @backoff.on_exception(backoff.expo, RateLimitException, logger=None)
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
            async with self.session.get(self.ENDPOINT + service, headers=await self._get_headers(), params=data) as resp:
                if resp.status == 401 and allow_retry:
                    await self._ensure_login(force_relogin=True)
                    return await self._do_api_call(method, service, data, allow_retry=False, ensure_keys=ensure_keys)
                elif resp.status == 429:
                    raise RateLimitException()
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

    def _clean_game(self, game: Game) -> Game:
        """Add the NULL tag to a game with no tags."""
        if not all(key in game for key in Game.__annotations__):
            raise BayesUnexpectedResponseException('game', game)

        if not game['tags']:
            game['tags'].append('NULL')
        return game

    async def get_tags(self) -> List[Tag]:
        """Return a list of tags that can be used to request games"""
        return self.SPECIAL_TAGS + await self._do_api_call('GET', 'api/v1/tags')

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
        return await self._do_api_call('GET', 'api/v1/games', params, ensure_keys=GetGamesResponse.__annotations__)

    async def get_all_games(self, *, tag: Optional[Tag] = None, tags: Optional[Iterable[Tag]] = None,
                            from_timestamp: Optional[Union[datetime, str]] = None,
                            to_timestamp: Optional[Union[datetime, str]] = None) \
            -> List[Game]:
        """Get all games with the given filters"""
        if tags is None:
            tags = []
        else:
            tags = list(tags)
        only_null = False
        if tag is not None:
            tags.append(tag)

        if not tags or tags == ['ALL']:
            tags = None
        elif tags == ["NULL"]:
            only_null = True
            tags = None
        elif "NULL" in tags or "ALL" in tags:
            raise ValueError("The special tags NULL and ALL must be requested alone.")

        data = await self.get_games(tags=tags, page_size=999,
                                    from_timestamp=from_timestamp,
                                    to_timestamp=to_timestamp)
        if data['count'] >= 999:
            page = 1
            while len(data['games']) < data['count']:
                newpage = await self.get_games(tags=tags, page=page, page_size=999,
                                               from_timestamp=from_timestamp,
                                               to_timestamp=to_timestamp)
                data['games'].extend(newpage['games'])
                if not newpage['games']:
                    break
                page += 1
        return [self._clean_game(game) for game in data['games'] if not (game['tags'] and only_null)]

    async def get_game(self, game_id: GameID) -> Game:
        """Get a game by its ID"""
        try:
            game = await self._do_api_call('GET', f'api/v1/games/{game_id}')
        except ClientResponseError as e:
            if e.status == 404:
                raise BadRequestException(f'Invalid Game ID: {game_id}')
            raise
        return self._clean_game(game)

    async def get_asset(self, game_id: GameID, asset: AssetType) -> bytes:
        """Get the bytes for an asset"""
        game = await self.get_game(game_id)
        if asset not in game['assets']:
            raise BadRequestException(f'Invalid asset type for game with ID {game_id}: {asset}')
        data = await self._do_api_call('GET', f'api/v1/games/{game_id}/download', {'type': asset}, ensure_keys=['url'])
        async with self.session.get(data['url']) as resp:
            return await resp.read()
