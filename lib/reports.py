import discord
from cachetools import LRUCache

from lib.jsondb import JSONDB

db = JSONDB()  # something something instancing

PRIORITY = {
    -1: "Resolved", 0: "P0: Critical", 1: "P1: Very High", 2: "P2: High", 3: "P3: Medium", 4: "P4: Low",
    5: "P5: Trivial", 6: "Pending/Other"
}
VERI_EMOJI = {
    1: "\u2705",  # WHITE HEAVY CHECK MARK
    -1: "\u274c",  # CROSS MARK
    0: "\u2139"  # INFORMATION SOURCE
}
TRACKER_CHAN = "360855116057673729"


class Report:
    message_cache = LRUCache(maxsize=100)

    def __init__(self, reporter: str, report_id: str, title: str, severity: int, verification: int, attachments: list,
                 message: str):
        self.reporter = reporter
        self.report_id = report_id
        self.title = title
        self.severity = severity
        self.verification = verification
        self.attachments = attachments
        self.message = message

    @classmethod
    def new(cls, reporter: str, report_id: str, title: str, attachments: list, message: str = None, severity: int = 6,
            verification: int = 0):
        return cls(reporter, report_id, title, severity, verification, attachments, message)

    @classmethod
    def from_dict(cls, report_dict):
        return cls(**report_dict)

    def to_dict(self):
        return {
            'reporter': self.reporter, 'report_id': self.report_id, 'title': self.title, 'severity': self.severity,
            'verification': self.verification, 'attachments': self.attachments, 'message': self.message
        }

    @classmethod
    def from_id(cls, report_id):
        reports = db.jget("reports", {})
        try:
            return cls.from_dict(reports[report_id])
        except KeyError:
            raise Exception("Report not found.")

    def commit(self):
        reports = db.jget("reports", {})
        reports[self.report_id] = self.to_dict()
        db.jset("reports", reports)

    def get_embed(self, detailed=False, ctx=None):
        embed = discord.Embed()
        embed.title = f"`{self.report_id}` {self.title}"
        embed.description = f"*{len(self.attachments)} notes*"
        embed.add_field(name="Added By", value=f"<@{self.reporter}>")
        embed.add_field(name="Priority", value=PRIORITY.get(self.severity, "Unknown"))
        embed.add_field(name="Verification", value=str(self.verification))
        embed.set_footer(text=f"Use ~report {self.report_id} for details.")
        if detailed:
            if not ctx:
                raise ValueError("Context not supplied for detailed call.")
            embed.description = f"*{len(self.attachments)} notes, showing first 5*"
            for attachment in self.attachments[:5]:
                user = ctx.message.server.get_member(attachment['author'])
                msg = attachment['msg'][:1020] or "No details."
                embed.add_field(name=f"{VERI_EMOJI.get(attachment['veri'], '')} {user}",
                                value=msg,
                                inline=False)

        return embed

    def canrepro(self, author, msg):
        attachment = {
            'author': author,
            'msg': msg,
            'veri': 1
        }
        self.verification += 1
        self.attachments.append(attachment)

    def cannotrepro(self, author, msg):
        attachment = {
            'author': author,
            'msg': msg,
            'veri': -1
        }
        self.verification -= 1
        self.attachments.append(attachment)

    def addnote(self, author, msg):
        attachment = {
            'author': author,
            'msg': msg,
            'veri': 0
        }
        self.attachments.append(attachment)

    async def get_message(self, ctx):
        if self.message in self.message_cache:
            return self.message_cache[self.message]
        else:
            msg = await ctx.bot.get_message(ctx.bot.get_channel(TRACKER_CHAN), self.message)
            if msg:
                Report.message_cache[self.message] = msg
            return msg

    async def update(self, ctx):
        await ctx.bot.edit_message(await self.get_message(ctx), embed=self.get_embed())


def get_next_report_num(identifier):
    id_nums = db.jget("reportnums", {})
    num = id_nums.get(identifier, 0) + 1
    id_nums[identifier] = num
    db.jset("reportnums", id_nums)
    return f"{num:0>3}"
