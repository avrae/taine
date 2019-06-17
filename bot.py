import os
import random
import re
import sys
import traceback

from discord.ext import commands
from discord.ext.commands import CommandNotFound

import constants
from lib.github import GitHubClient
from lib.jsondb import JSONDB
from lib.misc import ContextProxy
from lib.reports import get_next_report_num, Report


class Taine(commands.AutoShardedBot):
    def __init__(self, *args, **kwargs):
        super(Taine, self).__init__(*args, **kwargs)
        self.db = JSONDB()


bot = Taine(command_prefix="~")

TOKEN = os.environ.get("TOKEN")  # os.environ.get("TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
ORG_NAME = os.environ.get("ORG_NAME", "avrae")
REACTIONS = [
    "\U0001f640",  # scream_cat
    "\U0001f426",  # bird
    "\U0001f3f9",  # bow_and_arrow
    "\U0001f989",  # owl
    "\U0001f50d",  # mag
    "bugs:454031039375867925",
    "panic:354415867313782784",
    "\U0001f576",  # sunglasses
    "\U0001f575",  # spy
    "\U0001f4e9",  # envelope_with_arrow
    "\U0001f933",  # selfie
    "\U0001f916",  # robot
    "\U0001f409",  # dragon
]
EXTENSIONS = ("web.web", "cogs.owner", "cogs.voting", "cogs.repl")


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
    await ctx.message.channel.send(f"Error: {error}")
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


@bot.event
async def on_message(message):
    report_type = None
    match = None
    if message.channel.id == constants.BUG_CHAN:  # bug-reports
        match = re.match(r"\**What is the [Bb]ug\?\**:?\s?(.+?)(\n|$)", message.content)
        report_type = 'AVR'
    elif message.channel.id == constants.FEATURE_CHAN:  # feature-request
        match = re.match(r"\**Feature [Rr]equest\**:?\s?(.+?)(\n|$)", message.content)
        report_type = 'AFR'
    elif message.channel.id == constants.WEB_CHAN:  # web-bug-reports
        match = re.match(r"\**What is the [Bb]ug\?\**:?\s?(.+?)(\n|$)", message.content)
        report_type = 'WEB'
    if match:
        title = match.group(1).strip(" *")
        report_num = get_next_report_num(report_type)
        report_id = f"{report_type}-{report_num}"

        report = await Report.new(message.author.id, report_id, title,
                                  [{'author': message.author.id, 'msg': message.content, 'veri': 0}])
        if report_type != 'AFR':
            await report.post_to_github(ContextProxy(bot))
        await report.setup_message(bot)
        report.commit()
        await message.add_reaction(random.choice(REACTIONS))

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
    report.commit()
    await ctx.send(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(aliases=['up'])
async def upvote(ctx, _id, *, msg=''):
    """Adds an upvote to the selected feature request."""
    report = Report.from_id(_id)
    await report.upvote(ctx.message.author.id, msg, ctx)
    report.subscribe(ctx)
    report.commit()
    await ctx.send(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(aliases=['cnr'])
async def cannotrepro(ctx, _id, *, msg=''):
    """Adds nonreproduction to a report."""
    report = Report.from_id(_id)
    await report.cannotrepro(ctx.message.author.id, msg, ctx)
    report.subscribe(ctx)
    report.commit()
    await ctx.send(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(aliases=['down'])
async def downvote(ctx, _id, *, msg=''):
    """Adds a downvote to the selected feature request."""
    report = Report.from_id(_id)
    await report.downvote(ctx.message.author.id, msg, ctx)
    report.subscribe(ctx)
    report.commit()
    await ctx.send(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command()
async def note(ctx, _id, *, msg=''):
    """Adds a note to a report."""
    report = Report.from_id(_id)
    await report.addnote(ctx.message.author.id, msg, ctx)
    report.subscribe(ctx)
    report.commit()
    await ctx.send(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


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
    reports = bot.db.jget("reports", {})
    num_unsubbed = 0

    for _id, report in reports.items():
        if ctx.message.author.id in report.get('subscribers', []):
            report['subscribers'].remove(ctx.message.author.id)
            num_unsubbed += 1
            reports[_id] = report

    bot.db.jset("reports", reports)
    await ctx.send(f"OK, unsubscribed from {num_unsubbed} reports.")


if __name__ == '__main__':
    if not (TOKEN and GITHUB_TOKEN):
        print("token or github metadata not set.")
    else:
        GitHubClient.initialize(GITHUB_TOKEN, ORG_NAME)  # initialize
        for extension in EXTENSIONS:
            bot.load_extension(extension)
        bot.run(TOKEN)
