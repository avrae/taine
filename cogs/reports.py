import random
import re
from typing import Any, Awaitable, Callable, Optional, Protocol

import cachetools
import disnake
from boto3.dynamodb.conditions import Attr
from disnake.ext import commands

import constants
from lib import db
from lib.db import query, query_sync
from lib.misc import search_and_select
from lib.reports import Attachment, Report, get_next_report_num

BUG_RE = re.compile(r"\**What is the [Bb]ug\?\**:?\s*(.+?)(\n|$)")
FEATURE_RE = re.compile(r"\**Feature [Rr]equest\**:?\s*(.+?)(\n|$)")


# ==== typing ====
class ContextLikeT(Protocol):
    bot: 'bot.Taine'
    guild: Optional[disnake.Guild]
    channel: disnake.abc.Messageable
    author: disnake.User


ReportNoteMethodT = Callable[[int, str, ContextLikeT], Awaitable[None]]


# ==== helpers ====
class ReportCache(cachetools.TTLCache):
    def __missing__(self, key):
        to_search = []
        for report_data in query_sync(db.reports):
            to_search.append(Report.from_dict(report_data))
        self[key] = to_search
        return to_search


async def slash_report_autocomplete(inter: disnake.ApplicationCommandInteraction, arg: str):
    out = []
    for r in Reports.search_cache[inter.id]:
        if arg.lower() in r.report_id.lower() or arg.lower() in r.title.lower():
            name = f"{r.report_id} {r.title}"
            if len(name) > 100:
                name = f"{name[:96]}..."
            out.append(name)
    return out[:25]


def slash_report_converter(_, arg: str) -> Report:
    report_id, _ = arg.split(maxsplit=1)
    return Report.from_id(report_id)


def report_param(desc) -> commands.Param:
    return commands.Param(desc=desc, autocomplete=slash_report_autocomplete, converter=slash_report_converter)


# ==== cog ====
class Reports(commands.Cog):
    search_cache = ReportCache(16, 60)  # meh

    def __init__(self, bot):
        self.bot = bot

    # ==== event listeners ====
    @commands.Cog.listener()
    async def on_message(self, message):
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

            report = await Report.new(
                message.author.id, report_id, title,
                [Attachment(message.author.id, message.content + attach)], is_bug=is_bug, repo=repo)

            await report.setup_message(self.bot)
            report.commit()
            await message.add_reaction(random.choice(constants.REACTIONS))

    # ==== message commands ====
    async def common_note_impl(self, ctx, report_id, msg, report_method_getter: Callable[[Report], ReportNoteMethodT]):
        report = Report.from_id(report_id)
        await self.add_vote_to_report(ctx, report, msg, method=report_method_getter(report))
        if ctx.channel.id == report.message:  # do not confirm in a thread
            return
        await ctx.send(f"Ok, I've added a note to `{report.report_id}` - {report.title}.")

    @commands.command(name='canrepro', aliases=['cr'])
    async def canrepro(self, ctx, report_id, *, msg=''):
        """Adds reproduction steps to a bug report."""
        await self.common_note_impl(ctx, report_id, msg, lambda report: report.canrepro)

    @commands.command(name='upvote', aliases=['up'])
    async def upvote(self, ctx, report_id, *, msg=''):
        """Adds a positive vote to a feature request."""
        await self.common_note_impl(ctx, report_id, msg, lambda report: report.upvote)

    @commands.command(name='cannotrepro', aliases=['cnr'])
    async def cannotrepro(self, ctx, report_id, *, msg=''):
        """Notes that you were unable to reproduce the reported issue."""
        await self.common_note_impl(ctx, report_id, msg, lambda report: report.cannotrepro)

    @commands.command(name='downvote', aliases=['down'])
    async def downvote(self, ctx, report_id, *, msg=''):
        """Adds a negative vote to a feature request."""
        await self.common_note_impl(ctx, report_id, msg, lambda report: report.downvote)

    @commands.command(name='note')
    async def note(self, ctx, report_id, *, msg):
        """Adds a note to a report."""
        await self.common_note_impl(ctx, report_id, msg, lambda report: report.addnote)

    @commands.command(name="report")
    async def viewreport(self, ctx, _id):
        """Gets the detailed status of a report."""
        await ctx.send(embed=Report.from_id(_id).get_embed(True, ctx.guild))

    @commands.command(aliases=['sub'])
    async def subscribe(self, ctx, report_id):
        """Subscribes to a report."""
        report = Report.from_id(report_id)
        is_subscribed = await self.toggle_report_subscription(ctx, report)
        if is_subscribed:
            await ctx.send(f"OK, subscribed to `{report.report_id}` - {report.title}.")
        else:
            await ctx.send(f"OK, unsubscribed from `{report.report_id}` - {report.title}.")

    @commands.command()
    async def unsuball(self, ctx):
        """Unsubscribes from all reports."""
        num_unsubbed = await self.unsubscribe_from_all(ctx.author.id)
        await ctx.send(f"OK, unsubscribed from {num_unsubbed} reports.")

    @commands.command()
    async def search(self, ctx, *, q):
        """Searches for a report."""
        to_search = self.search_cache['cache']
        result = await search_and_select(ctx, to_search, q, key=lambda report: report.title)
        if result is None:
            return await ctx.send("Report not found.")
        await ctx.send(embed=result.get_embed(detailed=True, guild=ctx.guild))

    @commands.command()
    async def top(self, ctx, n: int = 10):
        """Searches for the top feature requests."""
        if n < 1 or n > 20:
            return await ctx.send("Invalid number.")
        await ctx.trigger_typing()
        embed = await self.build_top_reports_embed(ctx, n)
        await ctx.send(embed=embed)

    # ==== slash commands ====
    async def common_slash_note_impl(
        self,
        inter: disnake.ApplicationCommandInteraction,
        report: Report,
        msg: str,
        report_method_getter: Callable[[Report], ReportNoteMethodT]
    ):
        # noinspection PyTypeChecker
        await self.add_vote_to_report(inter, report, msg, method=report_method_getter(report))
        await inter.send(f"Ok, I've added a note to `{report.report_id}` - {report.title}.",
                         ephemeral=inter.channel.id == report.message)

    @commands.slash_command(name='cr')
    async def slash_canrepro(
        self,
        inter: disnake.ApplicationCommandInteraction,
        report: Any = report_param("The report to add a note to."),
        msg: str = commands.Param('', desc="The note to add.")
    ):
        """Adds reproduction steps to a bug report."""
        await self.common_slash_note_impl(inter, report, msg, lambda r: r.canrepro)

    @commands.slash_command(name='cnr')
    async def slash_cannotrepro(
        self,
        inter: disnake.ApplicationCommandInteraction,
        report: Any = report_param("The report to add a note to."),
        msg: str = commands.Param('', desc="The note to add.")
    ):
        """Notes that you were unable to reproduce the reported issue."""
        await self.common_slash_note_impl(inter, report, msg, lambda r: r.cannotrepro)

    @commands.slash_command(name='up')
    async def slash_upvote(
        self,
        inter: disnake.ApplicationCommandInteraction,
        report: Any = report_param("The report to add a note to."),
        msg: str = commands.Param('', desc="The note to add.")
    ):
        """Adds a positive vote to a feature request."""
        await self.common_slash_note_impl(inter, report, msg, lambda r: r.upvote)

    @commands.slash_command(name='down')
    async def slash_downvote(
        self,
        inter: disnake.ApplicationCommandInteraction,
        report: Any = report_param("The report to add a note to."),
        msg: str = commands.Param('', desc="The note to add.")
    ):
        """Adds a negative vote to a feature request."""
        await self.common_slash_note_impl(inter, report, msg, lambda r: r.downvote)

    @commands.slash_command(name='note')
    async def slash_addnote(
        self,
        inter: disnake.ApplicationCommandInteraction,
        report: Any = report_param("The report to add a note to."),
        msg: str = commands.Param(desc="The note to add.")
    ):
        """Adds a note to a report."""
        await self.common_slash_note_impl(inter, report, msg, lambda r: r.addnote)

    @commands.slash_command(name="report")
    async def slash_viewreport(
        self,
        inter: disnake.ApplicationCommandInteraction,
        report: Any = report_param("The report to view.")
    ):
        """Gets the detailed status of a report."""
        await inter.send(embed=report.get_embed(True, inter.guild))

    @commands.slash_command(name="subscribe")
    async def slash_subscribe(
        self,
        inter: disnake.ApplicationCommandInteraction,
        report: Any = report_param("The report to subscribe to.")
    ):
        """Subscribes to a report."""
        is_subscribed = await self.toggle_report_subscription(inter, report)
        if is_subscribed:
            await inter.send(
                f"OK, subscribed to `{report.report_id}` - {report.title}.",
                ephemeral=True)
        else:
            await inter.send(
                f"OK, unsubscribed from `{report.report_id}` - {report.title}.",
                ephemeral=True)

    @commands.slash_command(name="unsuball")
    async def unsuball(self, inter: disnake.ApplicationCommandInteraction):
        """Unsubscribes from all reports."""
        num_unsubbed = await self.unsubscribe_from_all(inter.author.id)
        await inter.send(f"OK, unsubscribed from {num_unsubbed} reports.", ephemeral=True)

    @commands.slash_command(name="top")
    async def top(
        self,
        inter: disnake.ApplicationCommandInteraction,
        n: int = commands.Param(desc="How many reports to view.", ge=1, le=20)
    ):
        """Searches for the top feature requests."""
        embed = await self.build_top_reports_embed(inter, n)
        await inter.send(embed=embed)

    # ==== implementations ====
    @staticmethod
    async def add_vote_to_report(
        ctx: ContextLikeT,
        report: Report,
        message: str,
        method: ReportNoteMethodT
    ) -> None:
        await method(ctx.author.id, message, ctx)
        report.subscribe(ctx)
        await report.update(ctx)
        report.commit()

    @staticmethod
    async def toggle_report_subscription(ctx, report):
        if ctx.author.id in report.subscribers:
            report.unsubscribe(ctx)
            report.commit()
            return False
        else:
            report.subscribe(ctx)
            report.commit()
            return True

    @staticmethod
    async def unsubscribe_from_all(user_id):
        num_unsubbed = 0
        sentinel = lek = object()

        fe = Attr("subscribers").contains(user_id)
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
                i = report['subscribers'].index(user_id)
                num_unsubbed += 1
                db.reports.update_item(
                    Key={"report_id": report['report_id']},
                    UpdateExpression=f"REMOVE subscribers[{i}]"
                )
        return num_unsubbed

    @staticmethod
    async def build_top_reports_embed(ctx, n):
        embed = disnake.Embed()
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
        return embed


def setup(bot):
    bot.add_cog(Reports(bot))
