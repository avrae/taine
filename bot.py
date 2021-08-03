import os
import random
import re
import sys
import traceback

import discord
import sentry_sdk
from boto3.dynamodb.conditions import Attr
from discord import Intents
from discord.ext import commands
from discord.ext.commands import CheckFailure, CommandInvokeError, CommandNotFound, UserInputError

import constants
from lib import db
from lib.db import query
from lib.github import GitHubClient
from lib.misc import search_and_select
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


intents = Intents.all()
bot = Taine(command_prefix="~", intents=intents)

EXTENSIONS = ("web.web", "cogs.owner", "cogs.reactions", "cogs.repl", "cogs.inline")
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
    if not isinstance(error, (ReportException, UserInputError, CheckFailure)):
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
        attach = "\n" + '\n'.join(f"\n{'!' if item.url.lower().endswith(('.png', '.jpg', '.gif')) else ''}"
                                  f"[{item.filename}]({item.url})" for item in message.attachments)

        report = await Report.new(message.author.id, report_id, title,
                                  [Attachment(message.author.id, message.content + attach)], is_bug=is_bug, repo=repo)

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


@bot.command()
async def search(ctx, *, q):
    """Searches for a report."""
    to_search = []
    async for report_data in query(db.reports):
        to_search.append(Report.from_dict(report_data))
    result = await search_and_select(ctx, to_search, q, key=lambda report: report.title)
    if result is None:
        return await ctx.send("Report not found.")
    await ctx.send(embed=result.get_embed(detailed=True, ctx=ctx))


@bot.command()
async def top(ctx, n: int = 10):
    """Searches for the top feature requests."""
    if n < 1 or n > 20:
        return await ctx.send("Invalid number.")

    await ctx.trigger_typing()

    embed = discord.Embed()
    embed.title = f"Top {n} Open Feature Requests"
    embed.description = "Click a report to jump to its tracker message."

    reports = []
    async for fr_data in query(db.reports, Attr("is_bug").eq(False) and Attr("severity").gte(0)):
        reports.append(Report.from_dict(fr_data))
    sorted_reports = sorted(reports, key=lambda r: r.score, reverse=True)[:n]
    last_field = []

    for report in sorted_reports:
        message = await report.get_message(ctx)
        if message is not None:
            report_str = f"`{report.score:+}` [`{report.report_id}` {report.title}]({message.jump_url})"
        else:
            report_str = f"`{report.score:+}` `{report.report_id}` {report.title}"

        if len(report_str) + sum(len(s) + 1 for s in last_field) > 1024:
            embed.add_field(name='** **', value='\n'.join(last_field), inline=False)
            last_field = [report_str]
        else:
            last_field.append(report_str)
    embed.add_field(name='** **', value='\n'.join(last_field), inline=False)

    await ctx.send(embed=embed)


if __name__ == '__main__':
    if not (DISCORD_TOKEN and GITHUB_TOKEN):
        print("Discord/Github configuration not set")
    else:
        GitHubClient.initialize(GITHUB_TOKEN, ORG_NAME)  # initialize
        for extension in EXTENSIONS:
            bot.load_extension(extension)
        bot.run(DISCORD_TOKEN)
