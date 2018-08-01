import re

import discord
from cachetools import LRUCache

from lib.github import GitHubClient
from lib.jsondb import JSONDB

db = JSONDB()  # something something instancing

PRIORITY = {
    -2: "Patch Pending", -1: "Resolved",
    0: "P0: Critical", 1: "P1: Very High", 2: "P2: High", 3: "P3: Medium", 4: "P4: Low", 5: "P5: Trivial",
    6: "Pending/Other"
}
PRIORITY_LABELS = {
    0: "P0: Critical", 1: "P1: Very High", 2: "P2: High", 3: "P3: Medium", 4: "P4: Low", 5: "P5: Trivial"
}
TYPE_LABELS = {
    "AVR": "bug", "AFR": "featurereq", "DDB": "bug"
}
VERI_EMOJI = {
    -2: "\u2b07",  # DOWNVOTE
    -1: "\u274c",  # CROSS MARK
    0: "\u2139",  # INFORMATION SOURCE
    1: "\u2705",  # WHITE HEAVY CHECK MARK
    2: "\u2b06",  # UPVOTE
}
VERI_KEY = {
    -2: "Downvote",
    -1: "Cannot Reproduce",
    0: "Note",
    1: "Can Reproduce",
    2: "Upvote"
}

TRACKER_CHAN = "360855116057673729"  # AVRAE DEV "360855116057673729"
GITHUB_BASE = "https://github.com"


class Report:
    message_cache = LRUCache(maxsize=100)

    def __init__(self, reporter: str, report_id: str, title: str, severity: int, verification: int, attachments: list,
                 message: str, upvotes: int = 0, downvotes: int = 0, github_issue: int = None):
        self.reporter = reporter
        self.report_id = report_id
        self.title = title
        self.severity = severity
        self.verification = verification
        self.upvotes = upvotes
        self.downvotes = downvotes
        self.attachments = attachments
        self.message = message
        self.github_issue = github_issue

    @classmethod
    async def new(cls, reporter: str, report_id: str, title: str, attachments: list, message: str = None,
                  severity: int = 6, verification: int = 0, author=None):
        inst = cls(reporter, report_id, title, severity, verification, attachments, message)
        labels = [l for l in [TYPE_LABELS.get(report_id[:3])] if l]
        if author:
            desc = f"{inst.get_github_desc()}\n\n- {author}"
        else:
            desc = inst.get_github_desc()
        issue = await GitHubClient.get_instance().create_issue(f"{report_id} {title}", desc, labels)
        inst.github_issue = issue.number
        return inst

    @classmethod
    def from_issue(cls, issue):
        attachments = [{
            "msg": issue['body'],
            "author": "GitHub",
            "veri": 0
        }]
        return cls("GitHub", f"AVR-{get_next_report_num('AVR')}", issue['title'], -1,
                   # pri is created at -1 for unresolve
                   0, attachments, None, 0, 0, issue['number'])

    @classmethod
    def from_dict(cls, report_dict):
        return cls(**report_dict)

    def to_dict(self):
        return {
            'reporter': self.reporter, 'report_id': self.report_id, 'title': self.title, 'severity': self.severity,
            'verification': self.verification, 'upvotes': self.upvotes, 'downvotes': self.downvotes,
            'attachments': self.attachments, 'message': self.message, 'github_issue': self.github_issue
        }

    @classmethod
    def from_id(cls, report_id):
        reports = db.jget("reports", {})
        try:
            return cls.from_dict(reports[report_id.upper()])
        except KeyError:
            raise ReportException("Report not found.")

    @classmethod
    def from_github(cls, issue_num):
        reports = db.jget("reports", {})
        try:
            return cls.from_dict(next(r for r in reports.values() if r.get('github_issue') == issue_num))
        except StopIteration:
            raise ReportException("Report not found.")

    def commit(self):
        reports = db.jget("reports", {})
        reports[self.report_id] = self.to_dict()
        db.jset("reports", reports)

    def get_embed(self, detailed=False, ctx=None):
        embed = discord.Embed()
        if re.match(r"\d+", self.reporter):
            embed.add_field(name="Added By", value=f"<@{self.reporter}>")
        else:
            embed.add_field(name="Added By", value=self.reporter)
        embed.add_field(name="Priority", value=PRIORITY.get(self.severity, "Unknown"))
        if self.report_id.startswith("AFR"):
            # These statements bought to you by: Dusk-Argentum! Dusk-Argentum: Added Useless Features since 2018!
            embed.colour = 0x00ff00
            embed.add_field(name="Votes", value="\u2b06" + str(self.upvotes) + "` | `\u2b07" + str(self.downvotes))
            embed.set_footer(text=f"~report {self.report_id} for details | Vote with ~up/~down {self.report_id} [note]")
        elif self.report_id.startswith("WEB"):
            embed.colour = 0x57235c
            embed.add_field(name="Votes", value="\u2b06" + str(self.upvotes) + "` | `\u2b07" + str(self.downvotes),
                            inline=True)
            embed.add_field(name="Verification", value=str(self.verification))
            embed.set_footer(text=f"~report {self.report_id} for details | "
                                  f"Verify with ~cr/~cnr {self.report_id} [note], "
                                  f"or vote with ~up/~down {self.report_id} [note]")
        else:
            if self.report_id.startswith("AVR"):
                embed.colour = 0xff0000
            elif self.report_id.startswith("DDB"):
                embed.colour = 0xe30910
            embed.add_field(name="Verification", value=str(self.verification))
            embed.set_footer(text=f"~report {self.report_id} for details | "
                                  f"Verify with ~cr/~cnr {self.report_id} [note]")

        embed.title = f"`{self.report_id}` {self.title}"
        if len(embed.title) > 256:
            embed.title = f"{embed.title[:250]}..."
        if self.github_issue:
            embed.url = f"{GITHUB_BASE}/{GitHubClient.get_instance().repo_name}/issues/{self.github_issue}"
        embed.description = f"*{len(self.attachments)} notes*"
        if detailed:
            if not ctx:
                raise ValueError("Context not supplied for detailed call.")
            embed.description = f"*{len(self.attachments)} notes, showing first 10*"
            for attachment in self.attachments[:10]:
                if re.match(r"\d+", attachment['author']):
                    user = ctx.message.server.get_member(attachment['author'])
                else:
                    user = attachment['author']
                msg = attachment['msg'][:1020] or "No details."
                embed.add_field(name=f"{VERI_EMOJI.get(attachment['veri'], '')} {user}",
                                value=msg)

        return embed

    def get_github_desc(self):
        if self.attachments:
            return self.attachments[0]['msg']
        return self.title

    async def add_attachment(self, ctx, attachment, add_to_github=True):
        self.attachments.append(attachment)
        if add_to_github and self.github_issue:
            username = str(
                next((m for m in ctx.bot.get_all_members() if m.id == attachment['author']), attachment['author']))
            msg = f"{VERI_KEY.get(attachment['veri'], '')} - {username}\n\n" \
                  f"{attachment['msg']}"
            await GitHubClient.get_instance().add_issue_comment(self.github_issue, msg)

    async def canrepro(self, author, msg, ctx):
        if [a for a in self.attachments if a['author'] == ctx and a['veri']]:
            raise ReportException("You have already verified this report.")
        attachment = {
            'author': author,
            'msg': msg,
            'veri': 1
        }
        self.verification += 1
        await self.add_attachment(ctx, attachment)

    async def upvote(self, author, msg, ctx):
        if [a for a in self.attachments if a['author'] == author and a['veri']]:
            raise ReportException("You have already upvoted this report.")
        attachment = {
            'author': author,
            'msg': msg,
            'veri': 2
        }
        self.upvotes += 1
        await self.add_attachment(ctx, attachment)

    async def cannotrepro(self, author, msg, ctx):
        if [a for a in self.attachments if a['author'] == author and a['veri']]:
            raise ReportException("You have already verified this report.")
        attachment = {
            'author': author,
            'msg': msg,
            'veri': -1
        }
        self.verification -= 1
        await self.add_attachment(ctx, attachment)

    async def downvote(self, author, msg, ctx):  # lol Dusk was here
        if [a for a in self.attachments if a['author'] == author and a['veri']]:
            raise ReportException("You have already downvoted this report.")
        attachment = {
            'author': author,
            'msg': msg,
            'veri': -2
        }
        self.downvotes += 1
        await self.add_attachment(ctx, attachment)

    async def addnote(self, author, msg, ctx, add_to_github=True):
        attachment = {
            'author': author,
            'msg': msg,
            'veri': 0
        }
        await self.add_attachment(ctx, attachment, add_to_github)

    async def get_message(self, ctx):
        if self.message is None:
            return None
        elif self.message in self.message_cache:
            return self.message_cache[self.message]
        else:
            msg = await ctx.bot.get_message(ctx.bot.get_channel(TRACKER_CHAN), self.message)
            if msg:
                Report.message_cache[self.message] = msg
            return msg

    async def update(self, ctx):
        await ctx.bot.edit_message(await self.get_message(ctx), embed=self.get_embed())

    async def resolve(self, ctx, msg='', close_github_issue=True, pend=False, ignore_closed=False):
        if self.severity == -1 and not ignore_closed:
            raise ReportException("This report is already closed.")

        self.severity = -1
        if msg:
            await self.addnote(ctx.message.author.id, f"Resolved - {msg}", ctx)

        msg_ = await self.get_message(ctx)
        if msg_:
            try:
                await ctx.bot.delete_message(msg_)
                if self.message in Report.message_cache:
                    del Report.message_cache[self.message]
            finally:
                self.message = None

        if close_github_issue and self.github_issue:
            await GitHubClient.get_instance().close_issue(self.github_issue)

        if pend:
            self.pend()

    async def unresolve(self, ctx, msg='', open_github_issue=True):
        if not self.severity == -1:
            raise ReportException("This report is still open.")

        self.severity = 6
        if msg:
            await self.addnote(ctx.message.author.id, f"Unresolved - {msg}", ctx)

        msg_ = await ctx.bot.send_message(ctx.bot.get_channel(TRACKER_CHAN), embed=self.get_embed())
        self.message = msg_.id

        if open_github_issue and self.github_issue:
            await GitHubClient.get_instance().open_issue(self.github_issue)

    def pend(self):
        pending = db.jget("pending-reports", [])
        pending.append(self.report_id)
        db.jset("pending-reports", pending)

    async def update_labels(self):
        labels = [TYPE_LABELS.get(self.report_id[:3]), PRIORITY_LABELS.get(self.severity)]
        labels = [l for l in labels if l]
        await GitHubClient.get_instance().label_issue(self.github_issue, labels)


def get_next_report_num(identifier):
    id_nums = db.jget("reportnums", {})
    num = id_nums.get(identifier, 0) + 1
    id_nums[identifier] = num
    db.jset("reportnums", id_nums)
    return f"{num:0>3}"


class ReportException(Exception):
    pass
