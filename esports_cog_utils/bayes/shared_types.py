import os
from datetime import datetime
from typing import Iterable, List, Literal, Optional, Tuple, TypedDict, Union

from aiohttp import ClientSession
from requests import Session

from .errors import BayesUnexpectedResponseException

RPGId = str
AssetType = Literal['GAMH_DETAILS', 'GAMH_SUMMARY', 'ROFL_REPLAY']
Tag = Union[str, Literal['NULL', 'ALL']]


class Game(TypedDict):
    platformGameId: RPGId
    name: str
    status: str
    createdAt: str  # ISO-8601 Formatted
    assets: List[AssetType]
    tags: List[Tag]
    blockName: str
    subBlockName: str
    teamTriCodes: List[str]


class GetGamesResponse(TypedDict):
    page: int
    size: int
    count: int
    games: List[Game]


# Arbitrarily large number.  Must be bigger than the total number of games in Bayes.
INFINITY = 99999


class Service:
    LOGIN = 'login'
    REFRESH = 'login/refresh_token'
    TAGS = 'api/v1/tags'
    GAMES = 'api/v1/games'
    GAME = f'{GAMES}/{{rpgid}}'
    ASSET = f'{GAMES}/{{rpgid}}/download'


class BaseBayesClient:
    ENDPOINT = 'https://emh-api.bayesesports.com/'
    SAVE_FILE = os.path.expanduser('~/.config/esports_wiki_cogs/bayes.json')
    SPECIAL_TAGS = ['NULL', 'ALL']

    def __init__(self, username: str, password: str, *, session: Union[ClientSession, Session] = None,
                 access_token: Optional[str] = None, refresh_token: Optional[str] = None,
                 expires: datetime = datetime.min):
        self.username = username
        self.password = password

        self.session = session

        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires = expires

    def _validate_tags(self, tag: Optional[Tag], tags: Optional[Iterable[Tag]]) -> Tuple[Optional[List[Tag]], bool]:
        if tags is None:
            tags = []
        else:
            tags = list(tags)
        only_null = False
        if tag is not None:
            tags.append(tag)

        if not tags or tags == ['ALL']:
            return None, False
        elif tags == ["NULL"]:
            return None, True
        elif "NULL" in tags or "ALL" in tags:
            raise ValueError("The special tags NULL and ALL must be requested alone.")
        return tags, False

    def _clean_game(self, game: Game) -> Game:
        """Add the NULL tag to a game with no tags."""
        if not all(key in game for key in Game.__annotations__):
            raise BayesUnexpectedResponseException('game', game)

        if not game['tags']:
            game['tags'].append('NULL')
        return game
