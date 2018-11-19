import copy

import discord
from discord.ext import commands

import constants
from lib.reports import Report, ReportException, get_next_report_num


class Owner:
    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True, aliases=['close'])
    async def resolve(self, ctx, _id, *, msg=''):
        """Owner only - Resolves a report."""
        if not ctx.message.author.id == constants.OWNER_ID:
            return
        report = Report.from_id(_id)
        await report.resolve(ctx, msg)
        report.commit()
        await self.bot.say(f"Resolved `{report.report_id}`: {report.title}.")

    @commands.command(pass_context=True, aliases=['open'])
    async def unresolve(self, ctx, _id, *, msg=''):
        """Owner only - Unresolves a report."""
        if not ctx.message.author.id == constants.OWNER_ID:
            return
        report = Report.from_id(_id)
        await report.unresolve(ctx, msg)
        report.commit()
        await self.bot.say(f"Unresolved `{report.report_id}`: {report.title}.")

    @commands.command(pass_context=True)
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
        msg = await self.bot.send_message(self.bot.get_channel(constants.TRACKER_CHAN), embed=new_report.get_embed())
        new_report.message = msg.id
        if new_report.github_issue:
            await new_report.update_labels()
            await new_report.edit_title(f"`{new_report.report_id}` {new_report.title}")
        new_report.commit()
        await self.bot.say(f"Reassigned {report.report_id} as {new_report.report_id}.")

    @commands.command(pass_context=True, aliases=['pri'])
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

        report.commit()
        await report.update(ctx)
        await self.bot.say(f"Changed priority of `{report.report_id}`: {report.title} to P{pri}.")

    @commands.command(pass_context=True, aliases=['pend'])
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
            report.commit()
            await report.update(ctx)
        if not not_found:
            await self.bot.say(f"Marked {len(reports)} reports as patch pending.")
        else:
            await self.bot.say(f"Marked {len(reports)} reports as patch pending. {not_found} reports were not found.")

    @commands.command(pass_context=True)
    async def update(self, ctx, build_id: int, *, msg=""):
        """Owner only - To be run after an update. Resolves all -P2 reports."""
        if not ctx.message.author.id == constants.OWNER_ID:
            return
        changelog = ""
        for _id in list(set(self.bot.db.jget("pending-reports", []))):
            report = Report.from_id(_id)
            await report.resolve(ctx, f"Patched in build {build_id}", ignore_closed=True)
            report.commit()
            action = "Fixed"
            if report.report_id.startswith("AFR"):
                action = "Added"
            if report.get_issue_link():
                changelog += f"- {action} [`{report.report_id}`]({report.get_issue_link()}) {report.title}\n"
            else:
                changelog += f"- {action} `{report.report_id}` {report.title}\n"
        changelog += msg

        self.bot.db.jset("pending-reports", [])
        await self.bot.send_message(ctx.message.channel,
                                    embed=discord.Embed(title=f"**Build {build_id}**", description=changelog,
                                                        colour=0x87d37c))
        await self.bot.delete_message(ctx.message)


def setup(bot):
    bot.add_cog(Owner(bot))