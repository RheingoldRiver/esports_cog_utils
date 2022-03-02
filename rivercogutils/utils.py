from typing import Optional

from mwrogue.esports_client import EsportsClient
from mwrogue.auth_credentials import AuthCredentials


async def get_credentials(ctx, bot) -> Optional[AuthCredentials]:
    gamepedia_keys = await bot.get_shared_api_tokens("gamepedia")
    if gamepedia_keys.get("account") is None:
        await ctx.send("Sorry, you haven't set a Gamepedia bot account yet.")
        return None
    username = "{}@{}".format(gamepedia_keys.get("account"), gamepedia_keys.get("bot"))
    password = gamepedia_keys.get("password")
    return AuthCredentials(username=username, password=password)


async def login_if_possible(ctx, bot, wiki) -> Optional[EsportsClient]:
    auth_credentials = await get_credentials(ctx, bot)
    if auth_credentials is None:
        return
    site = EsportsClient(wiki, credentials=auth_credentials)
    return site
