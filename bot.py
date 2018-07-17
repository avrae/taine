import os
import re

from discord.ext import commands

from lib.jsondb import JSONDB
from lib.reports import get_next_report_num, Report

bot = commands.Bot(command_prefix="~")
bot.db = JSONDB()

TOKEN = os.environ.get("TOKEN")
OWNER_ID = "187421759484592128"
BUG_CHAN = "336792750773239809"
FEATURE_CHAN = "297190603819843586"
TRACKER_CHAN = "360855116057673729"


@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')


@bot.event
async def on_message(message):
    report_type = None
    match = None
    if message.channel.id == BUG_CHAN:  # bug-reports
        match = re.match(r"\**What is the [Bb]ug\?\**:? ?(.+?)\n", message.content)
        report_type = 'AVR'
    elif message.channel.id == FEATURE_CHAN:  # feature-request
        match = re.match(r"\**Feature [Rr]equest\**\s?:?(.+?)\n", message.content)
        report_type = 'AFR'

    if match:
        title = match.group(1)
        report_num = get_next_report_num(report_type)
        report_id = f"{report_type}-{report_num}"

        report = Report.new(message.author.id, report_id, title,
                            [{'author': message.author.id, 'msg': message.content, 'veri': 0}])
        report_message = await bot.send_message(bot.get_channel(TRACKER_CHAN), embed=report.get_embed())
        report.message = report_message.id
        report.commit()

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

    report = Report.new(ctx.message.author.id, report_id, title,
                        [{'author': ctx.message.author.id, 'msg': details, 'veri': 0}])
    report_message = await bot.send_message(bot.get_channel(TRACKER_CHAN), embed=report.get_embed())
    report.message = report_message.id
    report.commit()

    await bot.say(f"Ok, submitting bug report. Keep track of `{report_id}`!")
    await bot.delete_messages(
        [whatis, severity, repro, context, whatis_prompt, severity_prompt, repro_prompt, context_prompt])


@bot.command(pass_context=True, name="report")
async def viewreport(ctx, _id):
    """Gets the detailed status of a report."""
    await bot.say(embed=Report.from_id(_id).get_embed(True, ctx))


@bot.command(pass_context=True, aliases=['upvote', 'cr'])
async def canrepro(ctx, _id, *, msg=''):
    """Adds reproduction to a report, or votes up a feature request."""
    report = Report.from_id(_id)
    report.canrepro(ctx.message.author.id, msg)
    report.commit()
    await bot.say(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(pass_context=True, aliases=['downvote', 'cnr'])
async def cannotrepro(ctx, _id, *, msg=''):
    """Adds nonreproduction to a report, or votes down a feature request."""
    report = Report.from_id(_id)
    report.cannotrepro(ctx.message.author.id, msg)
    report.commit()
    await bot.say(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(pass_context=True)
async def note(ctx, _id, *, msg=''):
    """Adds a note to a report."""
    report = Report.from_id(_id)
    report.addnote(ctx.message.author.id, msg)
    report.commit()
    await bot.say(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(pass_context=True)
async def resolve(ctx, _id, *, msg=''):
    """Owner only - Resolves a report."""
    if not ctx.message.author.id == OWNER_ID: return
    report = Report.from_id(_id)

    report.severity = -1
    if msg:
        report.addnote(ctx.message.author.id, f"Resolved - {msg}")

    msg = await report.get_message(ctx)
    if msg:
        await bot.delete_message(msg)
        report.message = None

    report.commit()
    await bot.say(f"Resolved `{report.report_id}`: {report.title}.")


@bot.command(pass_context=True)
async def priority(ctx, _id, pri: int, *, msg=''):
    """Owner only - Changes the priority of a report."""
    if not ctx.message.author.id == OWNER_ID: return
    report = Report.from_id(_id)

    report.severity = pri
    if msg:
        report.addnote(ctx.message.author.id, f"Priority changed to {pri} - {msg}")

    report.commit()
    await report.update(ctx)
    await bot.say(f"Changed priority of `{report.report_id}`: {report.title} to P{pri}.")


if __name__ == '__main__':
    if not TOKEN:
        print("token not set.")
    else:
        bot.run(TOKEN)
