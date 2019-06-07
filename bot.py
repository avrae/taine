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


class Taine(commands.Bot):
    def __init__(self, *args, **kwargs):
        super(Taine, self).__init__(*args, **kwargs)
        self.db = JSONDB()


bot = Taine(command_prefix="~")

TOKEN = os.environ.get("TOKEN")  # os.environ.get("TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = "avrae/avrae"
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
EXTENSIONS = ("web.web", "cogs.aliases", "cogs.owner", "cogs.voting")


@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')


@bot.event
async def on_command_error(error, ctx):
    if isinstance(error, CommandNotFound):
        return
    await bot.send_message(ctx.message.channel, f"Error: {error}")
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


@bot.event
async def on_message(message):
    report_type = None
    match = None
    if message.channel.id == constants.BUG_CHAN:  # bug-reports
        match = re.match(r"\**What[ 'i]+s the [Bb]ug\?\**:? ?(.+?)(\n|$)", message.content)
        report_type = 'AVR'
    elif message.channel.id == constants.FEATURE_CHAN:  # feature-request
        match = re.match(r"\**Feature [Rr]equest\**:?\s?(.+?)(\n|$)", message.content)
        report_type = 'AFR'
    elif message.channel.id == constants.DDB_CHAN:  # bug-hunting-ddb
        match = re.match(r"\**What is the [Bb]ug\?\**:? ?(.+?)(\n|$)", message.content)
        report_type = 'DDB'
    elif message.channel.id == constants.WEB_CHAN:  # web-bug-reports
        match = re.match(r"\**What is the [Bb]ug\?\**:? ?(.+?)(\n|$)", message.content)
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
        await bot.add_reaction(message, random.choice(REACTIONS))

    await bot.process_commands(message)


@bot.command(pass_context=True, name="report")
async def viewreport(ctx, _id):
    """Gets the detailed status of a report."""
    await bot.say(embed=Report.from_id(_id).get_embed(True, ctx))


@bot.command(pass_context=True, aliases=['cr'])
async def canrepro(ctx, _id, *, msg=''):
    """Adds reproduction to a report."""
    report = Report.from_id(_id)
    await report.canrepro(ctx.message.author.id, msg, ctx)
    report.subscribe(ctx)
    report.commit()
    await bot.say(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(pass_context=True, aliases=['up'])
async def upvote(ctx, _id, *, msg=''):
    """Adds an upvote to the selected feature request."""
    report = Report.from_id(_id)
    await report.upvote(ctx.message.author.id, msg, ctx)
    report.subscribe(ctx)
    report.commit()
    await bot.say(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(pass_context=True, aliases=['cnr'])
async def cannotrepro(ctx, _id, *, msg=''):
    """Adds nonreproduction to a report."""
    report = Report.from_id(_id)
    await report.cannotrepro(ctx.message.author.id, msg, ctx)
    report.subscribe(ctx)
    report.commit()
    await bot.say(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(pass_context=True, aliases=['down'])
async def downvote(ctx, _id, *, msg=''):
    """Adds a downvote to the selected feature request."""
    report = Report.from_id(_id)
    await report.downvote(ctx.message.author.id, msg, ctx)
    report.subscribe(ctx)
    report.commit()
    await bot.say(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(pass_context=True)
async def note(ctx, _id, *, msg=''):
    """Adds a note to a report."""
    report = Report.from_id(_id)
    await report.addnote(ctx.message.author.id, msg, ctx)
    report.subscribe(ctx)
    report.commit()
    await bot.say(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(pass_context=True)
async def attach(ctx, report_id, message_id):
    """Attaches a recent message to a report."""
    report = Report.from_id(report_id)
    try:
        msg = next(m for m in bot.messages if m.id == message_id)
    except StopIteration:
        return await bot.say("I cannot find that message.")
    await report.addnote(msg.author.id, msg.content, ctx)
    report.subscribe(ctx)
    report.commit()
    await bot.say(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(pass_context=True, aliases=['sub'])
async def subscribe(ctx, report_id):
    """Subscribes to a report."""
    report = Report.from_id(report_id)
    if ctx.message.author.id in report.subscribers:
        report.unsubscribe(ctx)
        await bot.say(f"OK, unsubscribed from `{report.report_id}` - {report.title}.")
    else:
        report.subscribe(ctx)
        await bot.say(f"OK, subscribed to `{report.report_id}` - {report.title}.")
    report.commit()


@bot.command(pass_context=True)
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
    await bot.say(f"OK, unsubscribed from {num_unsubbed} reports.")


if __name__ == '__main__':
    if not (TOKEN and GITHUB_TOKEN and GITHUB_REPO):
        print("token or github metadata not set.")
    else:
        GitHubClient.initialize(GITHUB_TOKEN, GITHUB_REPO)  # initialize
        for extension in EXTENSIONS:
            bot.load_extension(extension)
        bot.run(TOKEN)
