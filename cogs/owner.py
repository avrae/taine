import copy

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
        msg = await self.bot.get_channel(constants.TRACKER_CHAN).send(embed=new_report.get_embed())
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
            await report.edit_title(report.title)
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
                report = Report.from_id(_id)
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
            out.append(Report.from_dict(report_data).report_id)

        out = ', '.join(f"`{_id}`" for _id in out)
        await ctx.send(f"Pending reports: {out}")

    @commands.command()
    async def unpend(self, ctx, *reports):
        if not ctx.message.author.id == constants.OWNER_ID:
            return
        not_found = 0
        for _id in reports:
            try:
                report = Report.from_id(_id)
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

    @commands.command(aliases=['release'])
    async def update(self, ctx, build_id, *, msg=""):
        """Owner only - To be run after an update. Resolves all -P2 reports."""
        if not ctx.message.author.id == constants.OWNER_ID:
            return
        changelog = DiscordEmbedTextPaginator()

        async for report_data in query(db.reports, Attr("pending").eq(True)):  # find all pending=True reports
            report = Report.from_dict(report_data)
            await report.resolve(ctx, f"Patched in build {build_id}", ignore_closed=True)
            report.pending = False
            report.commit()

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

        await ctx.send(embed=embed)
        await ctx.message.delete()


def setup(bot):
    bot.add_cog(Owner(bot))
