import asyncio
import re

from aiohttp import web
from disnake.ext import commands

import constants
from lib.github import GitHubClient
from lib.misc import ContextProxy
from lib.reports import Report, ReportException

PRI_LABEL_NAMES = ("P0", "P1", "P2", "P3", "P4", "P5")
BUG_LABEL = "bug"
FEATURE_LABEL = "featurereq"
EXEMPT_LABEL = "enhancement"

# structured CI-result comment posted by avrae-data-entry's automation-test workflow (producer side of this contract)
AUTOMATION_RESULT_RE = re.compile(
    r"AUTOMATION_TEST_RESULT:\s*(?P<status>PASS|FAIL)"
    r"(?:\s*\r?\n\s*Reason:\s*(?P<reason>.*))?",
    re.IGNORECASE | re.DOTALL,
)

# structured resolution-failure comment posted by avrae-data-entry's resolve workflow on the
# original submission PR, when the automation's name couldn't be matched against gamedata
AUTOMATION_RESOLUTION_FAILED_RE = re.compile(
    r"AUTOMATION_RESOLUTION_FAILED:\s*(?P<reason>.*)",
    re.IGNORECASE | re.DOTALL,
)


def parse_automation_test_result(body):
    """Parses a structured automation CI-result comment; returns {status, reason} or None."""
    if not body:
        return None
    match = AUTOMATION_RESULT_RE.search(body)
    if match is None:
        return None
    return {"status": match.group("status").upper(), "reason": (match.group("reason") or "").strip()}


def parse_automation_resolution_failed(body):
    """Parses a structured resolution-failure comment; returns {reason} or None."""
    if not body:
        return None
    match = AUTOMATION_RESOLUTION_FAILED_RE.search(body)
    if match is None:
        return None
    return {"reason": (match.group("reason") or "").strip()}


class Web(commands.Cog):
    # this is probably a really hacky way to run a webhook handler, but eh
    def __init__(self, bot):
        self.bot = bot
        loop = self.bot.loop
        app = web.Application(loop=loop)
        app.router.add_post('/github', self.github_handler)
        app.router.add_get('/github', self.health_check)
        self.run_app(app, host="0.0.0.0", port=8378)  # taine's discrim, lol

    async def github_handler(self, request):
        if not request.headers.get("User-Agent", "").startswith("GitHub-Hookshot/"):
            return web.Response(status=403)
        event_type = request.headers["X-GitHub-Event"]
        data = await request.json()

        if event_type == "ping":
            print(f"Pinged by GitHub. {data['zen']}")
        elif event_type == "issues":
            await self.issues_handler(data)
        elif event_type == "issue_comment":
            await self.issue_comment_handler(data)

        return web.Response()

    async def health_check(self, _):
        return web.Response(body="Healthy")

    # ===== github: issue event =====
    async def issues_handler(self, data):
        repo_name = data['repository']['full_name']
        action = data['action']
        if repo_name not in constants.REPO_ID_MAP:  # this issue is on a repo we don't listen to
            return
        if data['sender']['login'] == constants.MY_GITHUB:  # don't react to my own changes
            return

        # we only really care about opened or closed
        if action == "closed":
            await self.report_closed(data)
        elif action in ("opened", "reopened"):
            await self.report_opened(data)
        elif action in ("labeled", "unlabeled"):
            await self.report_labeled(data)

    async def report_closed(self, data):
        issue = data['issue']
        issue_num = issue['number']
        repo_name = data['repository']['full_name']
        try:
            report = Report.from_github(repo_name, issue_num)
        except ReportException:  # report not found
            return  # oh well

        pend = data['sender']['login'] == constants.OWNER_GITHUB

        await report.resolve(ContextProxy(self.bot), close_github_issue=False, pend=pend)
        report.commit()

    async def report_opened(self, data):
        issue = data['issue']
        issue_num = issue['number']
        repo_name = data['repository']['full_name']
        # is the issue new?
        try:
            report = Report.from_github(repo_name, issue_num)
        except ReportException:  # report not found
            issue_labels = [lab['name'] for lab in issue['labels']]
            if EXEMPT_LABEL in issue_labels:
                return None

            report = Report.new_from_issue(repo_name, issue)
            if not issue['title'].startswith(report.report_id):
                formatted_title = f"{report.report_id} {report.title}"
                await GitHubClient.get_instance().rename_issue(repo_name, issue['number'], formatted_title)

            # await GitHubClient.get_instance().add_issue_to_project(report.github_issue, report.is_bug)
            await GitHubClient.get_instance().add_issue_comment(repo_name, issue['number'],
                                                                f"Tracked as `{report.report_id}`.")
            await report.update_labels()

        await report.unresolve(ContextProxy(self.bot), open_github_issue=False)
        report.commit()

        return report

    async def report_labeled(self, data):
        await asyncio.sleep(10)  # prevent a race condition when an issue is newly created
        issue = data['issue']
        issue_num = issue['number']
        repo_name = data['repository']['full_name']
        label_names = [l['name'] for l in issue['labels']]

        if len([l for l in label_names if any(n in l for n in PRI_LABEL_NAMES)]) > 1:
            return  # multiple priority labels
        if len([l for l in label_names if l in (BUG_LABEL, FEATURE_LABEL, EXEMPT_LABEL)]) > 1:
            return  # multiple type labels

        try:
            report = Report.from_github(repo_name, issue_num)
        except ReportException:  # report not found
            report = await self.report_opened(data)

        if report is None:  # this only happens if we try to create a report off an enhancement label
            return  # we don't want to track it anyway

        ctx = ContextProxy(self.bot)

        if EXEMPT_LABEL in label_names:  # issue changed from bug/fr to enhancement
            await report.untrack(ctx)
        else:
            priority = report.severity
            for i, pri in enumerate(PRI_LABEL_NAMES):
                if any(pri in n for n in label_names):
                    priority = i
                    break
            report.severity = priority
            report.is_bug = FEATURE_LABEL not in label_names
            await report.update(ctx)
            report.commit()

    # ===== github: issue_comment event (also fires for PR comments) =====
    async def issue_comment_handler(self, data):
        issue = data['issue']
        issue_num = issue['number']
        repo_name = data['repository']['full_name']
        comment = data['comment']
        action = data['action']
        username = comment['user']['login']
        if username == constants.MY_GITHUB:
            return  # don't infinitely add comments

        # only care about create
        if action == "created":
            try:
                report = Report.from_github(repo_name, issue_num)
            except ReportException:
                return  # oh well

            # automation PR comments: only a structured CI/resolution result is mirrored to Discord (to the thread)
            if report.is_automation:
                await self.relay_automation_result(report, comment['body'])
                return

            await report.addnote(f"GitHub - {username}", comment['body'], ContextProxy(self.bot), add_to_github=False)
            await report.update(ContextProxy(self.bot))
            report.commit()

    async def relay_automation_result(self, report, body):
        """Relays a structured automation result comment to the submission thread; returns True if handled."""
        name = report.automation_name or report.title

        test_result = parse_automation_test_result(body)
        if test_result is not None:
            if test_result["status"] == "PASS":
                msg = f"✅ Automated tests passed for **{name}**."
            else:
                msg = f"❌ Automated tests failed for **{name}**."
                if test_result["reason"]:
                    msg += f"\n> {test_result['reason']}"
                msg += (f"\nTo try again, post an updated **{name}** submission in this thread — "
                        f"it updates your existing submission instead of opening a new one.")
            await report.notify_thread(self.bot, msg)
            return True

        resolution_failure = parse_automation_resolution_failed(body)
        if resolution_failure is not None:
            msg = f"⚠️ Couldn't find a matching ability named **{name}** in the compendium."
            if resolution_failure["reason"]:
                msg += f"\n> {resolution_failure['reason']}"
            msg += (f"\nCheck the spelling, or add a disambiguating source like \"{name} (Source)\", "
                    f"then post an updated submission in this thread — since the name changes, "
                    f"it'll go through as a new submission rather than updating this one.")
            await report.notify_thread(self.bot, msg)
            return True

        return False

    def run_app(self, app, *, host='0.0.0.0', port=None, ssl_context=None, backlog=128):
        """Run an app"""
        if port is None:
            if not ssl_context:
                port = 8080
            else:
                port = 8443

        loop = app.loop

        handler = app.make_handler()
        server = loop.create_server(handler, host, port, ssl=ssl_context,
                                    backlog=backlog)
        loop.run_until_complete(asyncio.gather(server, app.startup()))

        scheme = 'https' if ssl_context else 'http'
        print("======== Running on {scheme}://{host}:{port}/ ========".format(scheme=scheme, host=host, port=port))


def setup(bot):
    bot.add_cog(Web(bot))
