import os
import random
import re
import sys
import traceback

import sentry_sdk
from boto3.dynamodb.conditions import Attr
from discord.ext import commands
from discord.ext.commands import CommandInvokeError, CommandNotFound

import constants
from lib import db
from lib.github import GitHubClient
from lib.reports import Attachment, Report, ReportException, get_next_report_num

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


bot = Taine(command_prefix="~")

EXTENSIONS = ("web.web", "cogs.owner", "cogs.reactions", "cogs.repl")
BUG_RE = re.compile(r"\**What is the [Bb]ug\?\**:?\s*(.+?)(\n|$)")
FEATURE_RE = re.compile(r"\**Feature [Rr]equest\**:?\s*(.+?)(\n|$)")


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
    if not isinstance(error, ReportException):
        bot.log_exception(error)

    await ctx.message.channel.send(f"Error: {error}")
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


@bot.event
async def on_message(message):
    identifier = None
    repo = None
    is_bug = None

    feature_match = FEATURE_RE.match(message.content)
    bug_match = BUG_RE.match(message.content)
    match = None

    if feature_match:
        match = feature_match
        is_bug = False
    elif bug_match:
        match = bug_match
        is_bug = True

    for chan in constants.BUG_LISTEN_CHANS:
        if message.channel.id == chan['id']:
            identifier = chan['identifier']
            repo = chan['repo']

    if match and identifier:
        title = match.group(1).strip(" *.\n")
        report_num = get_next_report_num(identifier)
        report_id = f"{identifier}-{report_num}"

        report = await Report.new(message.author.id, report_id, title,
                                  [Attachment(message.author.id, message.content)], is_bug=is_bug, repo=repo)
        if is_bug:
            await report.setup_github(await bot.get_context(message))

        await report.setup_message(bot)
        report.commit()
        await message.add_reaction(random.choice(constants.REACTIONS))

    await bot.process_commands(message)


@bot.command(name="report")
async def viewreport(ctx, _id):
    """Gets the detailed status of a report."""
    await ctx.send(embed=Report.from_id(_id).get_embed(True, ctx))


@bot.command(aliases=['cr'])
async def canrepro(ctx, _id, *, msg=''):
    """Adds reproduction to a report."""
    report = Report.from_id(_id)
    await report.canrepro(ctx.message.author.id, msg, ctx)
    report.subscribe(ctx)
    await report.update(ctx)
    report.commit()
    await ctx.send(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")


@bot.command(aliases=['up'])
async def upvote(ctx, _id, *, msg=''):
    """Adds an upvote to the selected feature request."""
    report = Report.from_id(_id)
    await report.upvote(ctx.message.author.id, msg, ctx)
    report.subscribe(ctx)
    await report.update(ctx)
    report.commit()
    await ctx.send(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")


@bot.command(aliases=['cnr'])
async def cannotrepro(ctx, _id, *, msg=''):
    """Adds nonreproduction to a report."""
    report = Report.from_id(_id)
    await report.cannotrepro(ctx.message.author.id, msg, ctx)
    report.subscribe(ctx)
    await report.update(ctx)
    report.commit()
    await ctx.send(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")


@bot.command(aliases=['down'])
async def downvote(ctx, _id, *, msg=''):
    """Adds a downvote to the selected feature request."""
    report = Report.from_id(_id)
    await report.downvote(ctx.message.author.id, msg, ctx)
    report.subscribe(ctx)
    await report.update(ctx)
    report.commit()
    await ctx.send(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")


@bot.command()
async def note(ctx, _id, *, msg=''):
    """Adds a note to a report."""
    report = Report.from_id(_id)
    await report.addnote(ctx.message.author.id, msg, ctx)
    report.subscribe(ctx)
    await report.update(ctx)
    report.commit()
    await ctx.send(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")


@bot.command(aliases=['sub'])
async def subscribe(ctx, report_id):
    """Subscribes to a report."""
    report = Report.from_id(report_id)
    if ctx.message.author.id in report.subscribers:
        report.unsubscribe(ctx)
        await ctx.send(f"OK, unsubscribed from `{report.report_id}` - {report.title}.")
    else:
        report.subscribe(ctx)
        await ctx.send(f"OK, subscribed to `{report.report_id}` - {report.title}.")
    report.commit()


@bot.command()
async def unsuball(ctx):
    """Unsubscribes from all reports."""
    num_unsubbed = 0
    sentinel = lek = object()

    fe = Attr("subscribers").contains(ctx.author.id)
    while lek is not None:
        if lek is sentinel:
            response = db.reports.scan(
                FilterExpression=fe
            )
        else:
            response = db.reports.scan(
                FilterExpression=fe,
                ExclusiveStartKey=lek
            )

        lek = response.get('LastEvaluatedKey')
        for report in response['Items']:
            i = report['subscribers'].index(ctx.author.id)
            num_unsubbed += 1
            db.reports.update_item(
                Key={"report_id": report['report_id']},
                UpdateExpression=f"REMOVE subscribers[{i}]"
            )

    await ctx.send(f"OK, unsubscribed from {num_unsubbed} reports.")


if __name__ == '__main__':
    if not (DISCORD_TOKEN and GITHUB_TOKEN):
        print("Discord/Github configuration not set")
    else:
        GitHubClient.initialize(GITHUB_TOKEN, ORG_NAME)  # initialize
        for extension in EXTENSIONS:
            bot.load_extension(extension)
        bot.run(DISCORD_TOKEN)
