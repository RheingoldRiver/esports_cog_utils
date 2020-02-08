from esportswiki_editing import login


async def login_if_possible(ctx, bot, wiki):
    gamepedia_keys = await bot.get_shared_api_tokens("gamepedia")
    if gamepedia_keys.get("account") is None:
        await ctx.send("Sorry, you haven't set a Gamepedia bot account yet.")
        return None
    username = "{}@{}".format(gamepedia_keys.get("account"), gamepedia_keys.get("bot"))
    password = gamepedia_keys.get("password")
    return login('me', wiki, username=username, pwd=password)
