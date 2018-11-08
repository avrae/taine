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
from lib.reports import get_next_report_num, Report

bot = commands.Bot(command_prefix="~")
bot.db = JSONDB()

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
EXTENSIONS = ("web.web", "cogs.aliases", "cogs.owner")


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
        match = re.match(r"\**What is the [Bb]ug\?\**:? ?(.+?)(\n|$)", message.content)
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
                                  [{'author': message.author.id, 'msg': message.content, 'veri': 0}],
                                  author=message.author)
        report_message = await bot.send_message(bot.get_channel(constants.TRACKER_CHAN), embed=report.get_embed())
        report.message = report_message.id
        report.commit()
        await bot.add_reaction(message, random.choice(REACTIONS))

    await bot.process_commands(message)


@bot.command(pass_context=True, no_pm=True)
async def bug(ctx):
    """Reports a bug."""
    try:
        whatis_prompt = await bot.reply("What is the bug? (Say a short description)")
        whatis = await bot.wait_for_message(timeout=300, author=ctx.message.author, channel=ctx.message.channel)
        assert whatis is not None

        def severity_check(msg):
            return msg.content.lower() in ('trivial', 'low', 'medium', 'high', 'critical', 'other')

        severity_prompt = await bot.reply(
            "What is severity of the bug? (Trivial (typos, etc) / Low (formatting issues, "
            "things that don't impact operation) / Medium (minor functional impact) / "
            "High (a broken feature, major functional impact) / "
            "Critical (bot crash, extremely major functional impact))")
        severity = await bot.wait_for_message(timeout=120, author=ctx.message.author, channel=ctx.message.channel,
                                              check=severity_check)
        assert severity is not None

        def len_check(maxlen):
            return lambda m: len(m.content) < maxlen

        repro_prompt = await bot.reply("How can I reproduce this bug? (Say a short description, 1024 char max)")
        repro = await bot.wait_for_message(timeout=300, author=ctx.message.author, channel=ctx.message.channel,
                                           check=len_check(1024))
        assert repro is not None

        context_prompt = await bot.reply("What is the context of the bug? "
                                         "(The command and any choice trees that led to the bug, "
                                         "256 char max)")
        context = await bot.wait_for_message(timeout=300, author=ctx.message.author, channel=ctx.message.channel,
                                             check=len_check(256))
        assert context is not None
    except AssertionError:
        return await bot.reply("Timed out waiting for a response.")

    report_id = f"AVR-{get_next_report_num('AVR')}"
    title = whatis.content
    details = f"**What is the bug?**: {title}\n" \
              f"**Severity**: {severity.content.title()}\n" \
              f"**Steps to reproduce**: {repro.content}\n" \
              f"**Context**: {context.content}"

    report = await Report.new(ctx.message.author.id, report_id, title,
                              [{'author': ctx.message.author.id, 'msg': details, 'veri': 0}], author=ctx.message.author)
    report_message = await bot.send_message(bot.get_channel(constants.TRACKER_CHAN), embed=report.get_embed())
    report.message = report_message.id
    report.commit()

    await bot.say(f"Ok, submitting bug report. Keep track of `{report_id}`!")
    await bot.delete_messages(
        [whatis, severity, repro, context, whatis_prompt, severity_prompt, repro_prompt, context_prompt])


@bot.command(pass_context=True, name="report")
async def viewreport(ctx, _id):
    """Gets the detailed status of a report."""
    await bot.say(embed=Report.from_id(_id).get_embed(True, ctx))


@bot.command(pass_context=True, aliases=['cr'])
async def canrepro(ctx, _id, *, msg=''):
    """Adds reproduction to a report."""
    report = Report.from_id(_id)
    await report.canrepro(ctx.message.author.id, msg, ctx)
    report.commit()
    await bot.say(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(pass_context=True, aliases=['up'])
async def upvote(ctx, _id, *, msg=''):
    """Adds an upvote to the selected feature request."""
    report = Report.from_id(_id)
    await report.upvote(ctx.message.author.id, msg, ctx)
    report.commit()
    await bot.say(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(pass_context=True, aliases=['cnr'])
async def cannotrepro(ctx, _id, *, msg=''):
    """Adds nonreproduction to a report."""
    report = Report.from_id(_id)
    await report.cannotrepro(ctx.message.author.id, msg, ctx)
    report.commit()
    await bot.say(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(pass_context=True, aliases=['down'])
async def downvote(ctx, _id, *, msg=''):
    """Adds a downvote to the selected feature request."""
    report = Report.from_id(_id)
    await report.downvote(ctx.message.author.id, msg, ctx)
    report.commit()
    await bot.say(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(pass_context=True)
async def note(ctx, _id, *, msg=''):
    """Adds a note to a report."""
    report = Report.from_id(_id)
    await report.addnote(ctx.message.author.id, msg, ctx)
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
    report.commit()
    await bot.say(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(pass_context=True, aliases=['sub'])
async def subscribe(ctx, report_id):
    """Subscribes to a report."""
    report = Report.from_id(report_id)
    author_id = ctx.message.author.id
    if author_id in report.subscribers:
        report.subscribers.remove(author_id)
        await bot.say(f"OK, unsubscribed from `{report.report_id}` - {report.title}.")
    else:
        report.subscribers.append(author_id)
        await bot.say(f"OK, subscribed to `{report.report_id}` - {report.title}.")
    report.commit()


if __name__ == '__main__':
    if not (TOKEN and GITHUB_TOKEN and GITHUB_REPO):
        print("token or github metadata not set.")
    else:
        GitHubClient.initialize(GITHUB_TOKEN, GITHUB_REPO)  # initialize
        for extension in EXTENSIONS:
            bot.load_extension(extension)
        bot.run(TOKEN)
