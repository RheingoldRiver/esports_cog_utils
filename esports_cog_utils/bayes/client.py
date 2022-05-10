from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Literal, Optional, Union

import backoff
from requests import HTTPError, Session

from .errors import BayesBadAPIKeyException, BayesBadRequestException, BayesRateLimitException, \
    BayesUnexpectedResponseException
from .static_types import AssetType, Game, GetGamesResponse, INFINITY, RPGId, Service, Tag


class BayesClient:
    ENDPOINT = "https://emh-api.bayesesports.com/"
    SPECIAL_TAGS = ['NULL', 'ALL']

    def __init__(self, username: str, password: str, *, session: Session = None,
                 access_token: Optional[str] = None, refresh_token: Optional[str] = None,
                 expires: datetime = datetime.min):
        self.username = username
        self.password = password

        self.session = session

        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires = expires

    def _ensure_login(self, force_relogin: bool = False) -> None:
        """Ensure that the access_token is recent and valid"""
        if force_relogin or self.access_token is None:
            try:
                data = self._do_api_call('POST', Service.LOGIN,
                                         {'username': self.username, 'password': self.password},
                                         ensure_keys=['accessToken', 'refreshToken', 'expiresIn'])
            except HTTPError as e:
                if e.response.status_code == 500:
                    raise BayesBadAPIKeyException()
                raise
            self.access_token = data['accessToken']
            self.refresh_token = data['refreshToken']
            self.expires = datetime.now() + timedelta(seconds=data['expiresIn'])
        elif self.expires <= datetime.now():
            data = self._do_api_call('POST', Service.REFRESH,
                                     {'refreshToken': self.refresh_token},
                                     ensure_keys=['accessToken', 'expiresIn'])
            self.access_token = data['accessToken']
            self.expires = datetime.now() + timedelta(seconds=data['expiresIn'])

    @backoff.on_exception(backoff.expo, BayesRateLimitException, logger=None)
    def _do_api_call(self, method: Literal['GET', 'POST'], service: str,
                     data: Dict[str, Any] = None, *, allow_retry: bool = True,
                     ensure_keys: Optional[Iterable[str]] = None):
        """Make a single API call to emh-api.bayesesports.com"""
        if data is None:
            data = {}
        if ensure_keys is None:
            ensure_keys = []

        if self.session is None:
            self.session = Session()
        if method == "GET":
            with self.session.get(self.ENDPOINT + service, headers=self._get_headers(), params=data) as resp:
                if resp.status_code == 401 and allow_retry:
                    self._ensure_login(force_relogin=True)
                    return self._do_api_call(method, service, data, allow_retry=False, ensure_keys=ensure_keys)
                elif resp.status_code == 429:
                    raise BayesRateLimitException()
                resp.raise_for_status()
                data = resp.json()
        elif method == "POST":
            with self.session.post(self.ENDPOINT + service, json=data) as resp:
                resp.raise_for_status()
                data = resp.json()
        else:
            raise ValueError("HTTP Method must be GET or POST.")
        if not all(key in data for key in ensure_keys):
            raise BayesUnexpectedResponseException(service, data)
        return data

    def _get_headers(self) -> Dict[str, str]:
        """Return headers for a GET request to the API"""
        self._ensure_login()
        return {'Authorization': f'Bearer {self.access_token}'}

    def _clean_game(self, game: Game) -> Game:
        """Add the NULL tag to a game with no tags."""
        if not all(key in game for key in Game.__annotations__):
            raise BayesUnexpectedResponseException('game', game)

        if not game['tags']:
            game['tags'].append('NULL')
        return game

    def get_tags(self) -> List[Tag]:
        """Return a list of tags that can be used to request games"""
        return self.SPECIAL_TAGS + self._do_api_call('GET', Service.TAGS)

    def get_games(self, *, page: Optional[int] = None, page_size: Optional[int] = None,
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
        return self._do_api_call('GET', Service.GAMES, params, ensure_keys=GetGamesResponse.__annotations__)

    def get_all_games(self, *, tag: Optional[Tag] = None, tags: Optional[Iterable[Tag]] = None,
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

        data = self.get_games(tags=tags, page_size=INFINITY,
                              from_timestamp=from_timestamp,
                              to_timestamp=to_timestamp)
        if data['count'] >= INFINITY:
            page = 1
            while len(data['games']) < data['count']:
                newpage = self.get_games(tags=tags, page=page, page_size=INFINITY,
                                         from_timestamp=from_timestamp,
                                         to_timestamp=to_timestamp)
                data['games'].extend(newpage['games'])
                if not newpage['games']:
                    break
                page += 1
        return [self._clean_game(game) for game in data['games'] if not (game['tags'] and only_null)]

    def get_game(self, rpgid: RPGId) -> Game:
        """Get a game by its ID"""
        try:
            game = self._do_api_call('GET', Service.GAME.format(rpgid=rpgid))
        except HTTPError as e:
            if e.response.status_code == 404:
                raise BayesBadRequestException(f'Invalid Game ID: {rpgid}')
            raise
        return self._clean_game(game)

    def get_asset(self, rpgid: RPGId, asset: AssetType) -> bytes:
        """Get the bytes for an asset"""
        game = self.get_game(rpgid)
        if asset not in game['assets']:
            raise BayesBadRequestException(f'Invalid asset type for game with ID {rpgid}: {asset}')
        data = self._do_api_call('GET', Service.ASSET.format(rpgid=rpgid), {'type': asset}, ensure_keys=['url'])
        with self.session.get(data['url']) as resp:
            return resp.content
