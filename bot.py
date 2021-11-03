import datetime
import logging
import os
import sys
import traceback
from math import floor, isfinite

import disnake
import sentry_sdk
from disnake import Intents
from disnake.ext import commands
from disnake.ext.commands import CheckFailure, CommandInvokeError, CommandNotFound, UserInputError

import constants
from lib.github import GitHubClient
from lib.reports import ReportException

ORG_NAME = os.environ.get("ORG_NAME", "avrae")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
SENTRY_DSN = os.getenv('SENTRY_DSN') or None


class Taine(commands.AutoShardedBot):
    def __init__(self, *args, **kwargs):
        super(Taine, self).__init__(*args, **kwargs)

        if SENTRY_DSN is not None:
            sentry_sdk.init(dsn=SENTRY_DSN, environment="Production")

    @staticmethod
    def log_exception(exception=None):
        if SENTRY_DSN is not None:
            sentry_sdk.capture_exception(exception)


intents = Intents.all()
bot = Taine(
    command_prefix="~",
    intents=intents,
    test_guilds=constants.SLASH_TEST_GUILDS,
    sync_commands_debug=False
)

log_formatter = logging.Formatter('%(levelname)s:%(name)s: %(message)s')
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(log_formatter)
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(handler)
log = logging.getLogger('bot')

EXTENSIONS = ("web.web", "cogs.reports", "cogs.owner", "cogs.reactions", "cogs.repl", "cogs.inline")


@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, CommandNotFound):
        return

    if isinstance(error, CommandInvokeError):
        error = error.original

    # send error to sentry.io
    if not isinstance(error, (ReportException, UserInputError, CheckFailure)):
        bot.log_exception(error)

    await ctx.message.channel.send(f"Error: {error}")
    for line in traceback.format_exception(type(error), error, error.__traceback__):
        log.warning(line)


@bot.event
async def on_slash_command_error(inter, error):
    if isinstance(error, CommandInvokeError):
        error = error.original

    # send error to sentry.io
    if not isinstance(error, (ReportException, UserInputError, CheckFailure)):
        bot.log_exception(error)

    await inter.response.send_message(f"Error: {error}")
    for line in traceback.format_exception(type(error), error, error.__traceback__):
        log.warning(line)


@bot.event
async def on_error(event, *args, **kwargs):
    for line in traceback.format_exception(*sys.exc_info()):
        log.warning(line)


@bot.event
async def on_message(message):
    await bot.process_commands(message)


@bot.slash_command()
async def ping(
    inter: disnake.ApplicationCommandInteraction
):
    """Returns the bot's latency to the Discord API."""
    now = datetime.datetime.utcnow()
    await inter.response.defer()  # this makes an API call, we use the RTT of that call as the latency
    delta = datetime.datetime.utcnow() - now
    httping = floor(delta.total_seconds() * 1000)
    wsping = floor(bot.latency * 1000) if isfinite(bot.latency) else "Unknown"
    await inter.followup.send(f"Pong.\nHTTP Ping = {httping} ms.\nWS Ping = {wsping} ms.")


if __name__ == '__main__':
    if not (DISCORD_TOKEN and GITHUB_TOKEN):
        print("Discord/Github configuration not set")
    else:
        GitHubClient.initialize(GITHUB_TOKEN, ORG_NAME)  # initialize
        for extension in EXTENSIONS:
            bot.load_extension(extension)
        bot.run(DISCORD_TOKEN)
