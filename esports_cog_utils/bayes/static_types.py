from typing import List, Literal, TypedDict, Union

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
