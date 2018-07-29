import asyncio

from aiohttp import web

from lib.github import GitHubClient
from lib.reports import Report, ReportException


class Web:
    # this is probably a really hacky way to run a webhook handler, but eh
    def __init__(self, bot):
        self.bot = bot
        loop = self.bot.loop
        app = web.Application(loop=loop)
        app.router.add_post('/github', self.github_handler)
        self.run_app(app, host="127.0.0.1", port=8378)  # taine's discrim, lol

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

    async def issues_handler(self, data):
        issue = data['issue']
        issue_num = issue['number']
        action = data['action']
        if issue['user']['login'] == 'taine-bot':
            return

        # we only really care about opened or closed
        if action == "closed":
            try:
                report = Report.from_github(issue_num)
            except ReportException:  # report not found
                return  # oh well

            await report.resolve(ContextProxy(self.bot), None, False)
            report.commit()
        elif action in ("opened", "reopened"):
            # is the issue new?
            try:
                report = Report.from_github(issue_num)
            except ReportException:  # report not found
                report = Report.from_issue(issue)
                await GitHubClient.get_instance().add_issue_comment(issue['number'],
                                                                    f"Tracked as `{report.report_id}`.")

            await report.unresolve(ContextProxy(self.bot), None, False)
            report.commit()

    async def issue_comment_handler(self, data):
        issue = data['issue']
        issue_num = issue['number']
        comment = data['comment']
        action = data['action']
        username = comment['user']['login']
        if username == "taine-bot":
            return  # don't infinitely add comments

        # only care about create
        if action == "created":
            try:
                report = Report.from_github(issue_num)
            except ReportException:
                return  # oh well

            await report.addnote(f"GitHub - {username}", comment['body'], False)
            report.commit()
            await report.update(ContextProxy(self.bot))

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
        loop.run_until_complete(asyncio.gather(server, app.startup(), loop=loop))

        scheme = 'https' if ssl_context else 'http'
        print("======== Running on {scheme}://{host}:{port}/ ========".format(scheme=scheme, host=host, port=port))


class ContextProxy:  # just to pass the bot on to functions that need it
    def __init__(self, bot):
        self.bot = bot


def setup(bot):
    bot.add_cog(Web(bot))
