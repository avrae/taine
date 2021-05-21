import copy
import time

import discord
from boto3.dynamodb.conditions import Attr
from discord.ext import commands

import constants
from lib import db
from lib.db import query
from lib.reports import Report, ReportException, get_next_report_num
from utils import DiscordEmbedTextPaginator


class Owner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['close'])
    async def resolve(self, ctx, _id, *, msg=''):
        """Owner only - Resolves a report."""
        if not ctx.message.author.id == constants.OWNER_ID:
            return
        report = Report.from_id(_id)
        await report.resolve(ctx, msg)
        report.commit()
        await ctx.send(f"Resolved `{report.report_id}`: {report.title}.")

    @commands.command(aliases=['open'])
    async def unresolve(self, ctx, _id, *, msg=''):
        """Owner only - Unresolves a report."""
        if not ctx.message.author.id == constants.OWNER_ID:
            return
        report = Report.from_id(_id)
        await report.unresolve(ctx, msg)
        report.commit()
        await ctx.send(f"Unresolved `{report.report_id}`: {report.title}.")

    @commands.command(aliases=['reassign'])
    async def reidentify(self, ctx, report_id, identifier):
        """Owner only - Changes the identifier of a report."""
        if not ctx.message.author.id == constants.OWNER_ID:
            return

        identifier = identifier.upper()
        id_num = get_next_report_num(identifier)

        report = Report.from_id(report_id)
        new_report = copy.copy(report)
        await report.resolve(ctx, f"Reassigned as `{identifier}-{id_num}`.", False)
        report.commit()

        new_report.report_id = f"{identifier}-{id_num}"
        msg = await new_report.setup_message(self.bot)
        new_report.message = msg.id
        if new_report.github_issue:
            await new_report.update_labels()
            await new_report.edit_title(new_report.title)
        new_report.commit()
        await ctx.send(f"Reassigned {report.report_id} as {new_report.report_id}.")

    @commands.command()
    async def rename(self, ctx, report_id, *, name):
        """Owner only - Changes the title of a report."""
        if not ctx.message.author.id == constants.OWNER_ID:
            return

        report = Report.from_id(report_id)
        if report.github_issue:
            await report.edit_title(name)
        else:
            report.title = name
        await report.update(ctx)
        report.commit()
        await ctx.send(f"Renamed {report.report_id} as {report.title}.")

    @commands.command(aliases=['pri'])
    async def priority(self, ctx, _id, pri: int, *, msg=''):
        """Owner only - Changes the priority of a report."""
        if not ctx.message.author.id == constants.OWNER_ID:
            return
        report = Report.from_id(_id)

        report.severity = pri
        if msg:
            await report.addnote(ctx.message.author.id, f"Priority changed to {pri} - {msg}", ctx)

        if report.github_issue:
            await report.update_labels()
        await report.update(ctx)
        report.commit()
        await ctx.send(f"Changed priority of `{report.report_id}`: {report.title} to P{pri}.")

    @commands.group(aliases=['pend'], invoke_without_command=True)
    async def pending(self, ctx, *reports):
        """Owner only - Marks reports as pending for next patch."""
        if not ctx.message.author.id == constants.OWNER_ID:
            return
        not_found = 0
        for _id in reports:
            try:
                report = Report.from_id(_id.strip(', '))
            except ReportException:
                not_found += 1
                continue
            report.pend()
            await report.update(ctx)
            report.commit()
        if not not_found:
            await ctx.send(f"Marked {len(reports)} reports as patch pending.")
        else:
            await ctx.send(f"Marked {len(reports)} reports as patch pending. {not_found} reports were not found.")

    @pending.command(name="list")
    async def pending_list(self, ctx):
        out = []
        async for report_data in query(db.reports, Attr("pending").eq(True)):
            out.append(Report.from_dict(report_data))

        out_list = ', '.join(f"`{report.report_id}`" for report in out)
        detailed = '\n'.join(f"`{report.report_id}`: {report.title}" for report in out)
        await ctx.send(f"Pending reports: {out_list}\n{detailed}")

    @commands.command()
    async def unpend(self, ctx, *reports):
        if not ctx.message.author.id == constants.OWNER_ID:
            return
        not_found = 0
        for _id in reports:
            try:
                report = Report.from_id(_id.strip(', '))
            except ReportException:
                not_found += 1
                continue
            report.unpend()
            await report.update(ctx)
            report.commit()
        if not not_found:
            await ctx.send(f"Unpended {len(reports)} reports.")
        else:
            await ctx.send(f"Unpended {len(reports) - not_found} reports. {not_found} reports were not found.")

    async def _generate_changelog(self, build_id, msg, coro_for_each=None):
        """Generates a changelog, optionally running a coro for each report with the report as the sole arg."""
        changelog = DiscordEmbedTextPaginator()

        async for report_data in query(db.reports, Attr("pending").eq(True)):  # find all pending=True reports
            report = Report.from_dict(report_data)
            if coro_for_each:
                await coro_for_each(report)

            action = "Fixed"
            if not report.is_bug:
                action = "Added"
            if link := report.get_issue_link():
                changelog.add(f"- {action} [`{report.report_id}`]({link}) {report.title}")
            else:
                changelog.add(f"- {action} `{report.report_id}` {report.title}")

        changelog.add(msg)

        embed = discord.Embed(title=f"**Build {build_id}**", colour=0x87d37c)
        changelog.write_to(embed)
        return embed

    @commands.command(aliases=['release'])
    async def update(self, ctx, build_id, *, msg=""):
        """Owner only - To be run after an update. Resolves all -P2 reports."""
        if not ctx.message.author.id == constants.OWNER_ID:
            return

        async def resolver(report):
            await report.resolve(ctx, ignore_closed=True)
            report.pending = False
            report.commit()

        embed = await self._generate_changelog(build_id, msg, resolver)
        await ctx.send(embed=embed)
        await ctx.message.delete()

    @commands.command()
    async def dryrun(self, ctx, build_id, *, msg=""):
        """Owner only - changelog dryrun."""
        if not ctx.message.author.id == constants.OWNER_ID:
            return
        embed = await self._generate_changelog(build_id, msg)
        await ctx.send(embed=embed)

    @commands.command()
    async def reset_messages(self, ctx, yes):
        """Owner only - recreate all report messages. Takes some time! Pass "yes" as first arg."""
        if not ctx.message.author.id == constants.OWNER_ID:
            return

        if yes != 'yes':
            return

        await ctx.trigger_typing()

        start = time.monotonic()
        reports = []
        async for data in query(db.reports, Attr("severity").gte(0)):
            reports.append(Report.from_dict(data))

        for report in sorted(reports, key=lambda r: r.report_id):
            await report.setup_message(self.bot)
            report.commit()

        end = time.monotonic()
        t = end - start
        await ctx.send(f'done, setup {len(reports)} messages in {t} seconds')


def setup(bot):
    bot.add_cog(Owner(bot))
