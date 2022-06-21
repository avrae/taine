from disnake.ext import commands

from constants import OWNER_IDS

# ===== predicates =====


def author_is_owner(ctx):
    return ctx.author.id in OWNER_IDS

# ===== checks =====


def is_owner():
    def predicate(ctx):
        if author_is_owner(ctx):
            return True
        raise commands.CheckFailure("Only the bot owner may run this command.")

    return commands.check(predicate)
