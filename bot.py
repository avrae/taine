import copy
import os
import random
import re

from discord.ext import commands
from discord.ext.commands import CommandNotFound

from lib.github import GitHubClient
from lib.jsondb import JSONDB
from lib.reports import get_next_report_num, Report, ReportException

bot = commands.Bot(command_prefix="~")
bot.db = JSONDB()

TOKEN = os.environ.get("TOKEN")  # os.environ.get("TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = "avrae/avrae"
OWNER_ID = "187421759484592128"  # ZHU "187421759484592128"
BUG_CHAN = "336792750773239809"  # AVRAE DEV "336792750773239809" Make sure all 4 of these are unique, or else
DDB_CHAN = "463580965810208768"  # AVRAE DEV "463580965810208768" the bot might not work properly!
FEATURE_CHAN = "297190603819843586"  # AVRAE DEV "297190603819843586"
WEB_CHAN = "487486995527106580" # AVRAE DEV "487486995527106580"
TRACKER_CHAN = "360855116057673729"  # AVRAE DEV "360855116057673729"
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
    elif message.channel.id == DDB_CHAN:  # bug-hunting-ddb
        match = re.match(r"\**What is the [Bb]ug\?\**:? ?(.+?)\n", message.content)
        report_type = 'DDB'
    elif message.channel.id == WEB_CHAN: #web-bug-reports
        match = re.match(r"\**What is the [Bb]ug\?\**:? ?(.+?)\n", message.content)
        report_type = 'WEB'
    if match:
        title = match.group(1)
        report_num = get_next_report_num(report_type)
        report_id = f"{report_type}-{report_num}"

        report = await Report.new(message.author.id, report_id, title,
                                  [{'author': message.author.id, 'msg': message.content, 'veri': 0}])
        report_message = await bot.send_message(bot.get_channel(TRACKER_CHAN), embed=report.get_embed())
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


@bot.command(pass_context=True, aliases=['cr'])
async def canrepro(ctx, _id, *, msg=''):
    """Adds reproduction to a report."""
    report = Report.from_id(_id)
    await report.canrepro(ctx.message.author.id, msg)
    report.commit()
    await bot.say(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(pass_context=True, aliases=['up'])
async def upvote(ctx, _id, *, msg=''):
    """Adds an upvote to the selected feature request."""
    report = Report.from_id(_id)
    await report.upvote(ctx.message.author.id, msg)
    report.commit()
    await bot.say(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(pass_context=True, aliases=['cnr'])
async def cannotrepro(ctx, _id, *, msg=''):
    """Adds nonreproduction to a report."""
    report = Report.from_id(_id)
    await report.cannotrepro(ctx.message.author.id, msg)
    report.commit()
    await bot.say(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(pass_context=True, aliases=['down'])
async def downvote(ctx, _id, *, msg=''):
    """Adds a downvote to the selected feature request."""
    report = Report.from_id(_id)
    await report.downvote(ctx.message.author.id, msg)
    report.commit()
    await bot.say(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(pass_context=True)
async def note(ctx, _id, *, msg=''):
    """Adds a note to a report."""
    report = Report.from_id(_id)
    await report.addnote(ctx.message.author.id, msg)
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
    await report.addnote(msg.author.id, msg.content)
    report.commit()
    await bot.say(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")
    await report.update(ctx)


@bot.command(pass_context=True, aliases=['close'])
async def resolve(ctx, _id, *, msg=''):
    """Owner only - Resolves a report."""
    if not ctx.message.author.id == OWNER_ID: return
    report = Report.from_id(_id)
    await report.resolve(ctx, msg)
    report.commit()
    await bot.say(f"Resolved `{report.report_id}`: {report.title}.")


@bot.command(pass_context=True, aliases=['open'])
async def unresolve(ctx, _id, *, msg=''):
    """Owner only - Unresolves a report."""
    if not ctx.message.author.id == OWNER_ID: return
    report = Report.from_id(_id)
    await report.unresolve(ctx, msg)
    report.commit()
    await bot.say(f"Unresolved `{report.report_id}`: {report.title}.")


@bot.command(pass_context=True)
async def reidentify(ctx, report_id, identifier):
    """Owner only - Changes the identifier of a report."""
    if not ctx.message.author.id == OWNER_ID: return

    identifier = identifier.upper()
    id_num = get_next_report_num(identifier)

    report = Report.from_id(report_id)
    new_report = copy.copy(report)
    await report.resolve(ctx, f"Reassigned as `{identifier}-{id_num}`.", False)
    report.commit()

    new_report.report_id = f"{identifier}-{id_num}"
    msg = await bot.send_message(bot.get_channel(TRACKER_CHAN), embed=new_report.get_embed())
    new_report.message = msg.id
    new_report.commit()
    await bot.say(f"Reassigned {report.report_id} as {new_report.report_id}.")


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


@bot.command(pass_context=True, aliases=['pend'])
async def pending(ctx, *reports):
    """Owner only - Marks reports as pending for next patch."""
    if not ctx.message.author.id == OWNER_ID: return
    not_found = 0
    for _id in reports:
        try:
            report = Report.from_id(_id)
        except ReportException:
            not_found += 1
            continue
        report.severity = -2
        report.commit()
        await report.update(ctx)
    if not not_found:
        await bot.say(f"Marked {len(reports)} reports as patch pending.")
    else:
        await bot.say(f"Marked {len(reports)} reports as patch pending. {not_found} reports were not found.")


@bot.command(pass_context=True)
async def update(ctx, build_id: int):
    """Owner only - To be run after an update. Resolves all -P2 reports."""
    if not ctx.message.author.id == OWNER_ID: return
    changelog = f"**Build {build_id}**\n"
    for _id, raw_report in bot.db.jget("reports", {}).items():
        report = Report.from_dict(raw_report)
        if not report.severity == -2:
            continue
        await report.resolve(ctx, f"Patched in build {build_id}")
        report.commit()
        changelog += f"- `{report.report_id}` {report.title}\n"
    await bot.send_message(ctx.message.channel, changelog)
    await bot.delete_message(ctx.message)


if __name__ == '__main__':
    if not (TOKEN and GITHUB_TOKEN and GITHUB_REPO):
        print("token or github metadata not set.")
    else:
        GitHubClient.initialize(GITHUB_TOKEN, GITHUB_REPO)  # initialize
        bot.load_extension("web.web")
        bot.run(TOKEN)
