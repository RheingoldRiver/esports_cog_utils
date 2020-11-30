from river_mwclient.esports_client import EsportsClient
from river_mwclient.auth_credentials import AuthCredentials


async def login_if_possible(ctx, bot, wiki) -> EsportsClient:
    gamepedia_keys = await bot.get_shared_api_tokens("gamepedia")
    if gamepedia_keys.get("account") is None:
        await ctx.send("Sorry, you haven't set a Gamepedia bot account yet.")
        return None
    username = "{}@{}".format(gamepedia_keys.get("account"), gamepedia_keys.get("bot"))
    password = gamepedia_keys.get("password")
    credentials = AuthCredentials(username=username, password=password)
    site = EsportsClient(wiki, credentials=credentials)
    return site
