import asyncio

from github import Github, GithubException
from github.Repository import Repository


class GitHubClient:
    _instance = None

    def __init__(self, access_token, org):
        self.client = Github(access_token)
        self.repos = {}
        org = self.client.get_organization(org)

        self.bug_project = None
        self.feature_project = None

        for repo in org.get_repos("all"):  # build a method to access our repos
            print(f"Loaded repo {repo.full_name}")
            self.repos[repo.full_name] = repo

        # for project in org.get_projects():  # load the bug and feature projects
        #     if project.number == constants.BUG_PROJECT_ID:
        #         self.bug_project = project
        #     if project.number == constants.FEATURE_PROJECT_ID:
        #         self.feature_project = project

    @classmethod
    def initialize(cls, access_token, org='avrae'):
        if cls._instance:
            raise RuntimeError("Client already initialized")
        inst = cls(access_token, org)
        cls._instance = inst
        return inst

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            raise RuntimeError("Client not initialized")
        return cls._instance

    def get_repo(self, repo, default='avrae/avrae'):
        return self.repos.get(repo, self.repos.get(default))

    async def create_issue(self, repo, title, description, labels=None):
        if labels is None:
            labels = []
        if not isinstance(repo, Repository):
            repo = self.get_repo(repo)

        def _():
            return repo.create_issue(title, description, labels=labels)

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def add_issue_comment(self, repo, issue_num, description):
        if not isinstance(repo, Repository):
            repo = self.get_repo(repo)

        def _():
            issue = repo.get_issue(issue_num)
            return issue.create_comment(description)

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def label_issue(self, repo, issue_num, labels):
        if not isinstance(repo, Repository):
            repo = self.get_repo(repo)

        def _():
            issue = repo.get_issue(issue_num)
            issue.edit(labels=labels)

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def get_issue_labels(self, repo, issue_num):
        """Gets a list of issue label names."""
        if not isinstance(repo, Repository):
            repo = self.get_repo(repo)

        def _():
            issue = repo.get_issue(issue_num)
            return [lab.name for lab in issue.labels]

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def close_issue(self, repo, issue_num, comment=None):
        if not isinstance(repo, Repository):
            repo = self.get_repo(repo)

        def _():
            issue = repo.get_issue(issue_num)
            if comment:
                issue.create_comment(comment)
            issue.edit(state="closed")

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def open_issue(self, repo, issue_num, comment=None):
        if not isinstance(repo, Repository):
            repo = self.get_repo(repo)

        def _():
            issue = repo.get_issue(issue_num)
            if comment:
                issue.create_comment(comment)
            issue.edit(state="open")

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def rename_issue(self, repo, issue_num, new_title):
        if not isinstance(repo, Repository):
            repo = self.get_repo(repo)

        def _():
            issue = repo.get_issue(issue_num)
            issue.edit(title=new_title)

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def edit_issue_body(self, repo, issue_num, new_body):
        if not isinstance(repo, Repository):
            repo = self.get_repo(repo)

        def _():
            issue = repo.get_issue(issue_num)
            issue.edit(body=new_body)

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def add_issue_to_project(self, issue_num, is_bug):

        def _():
            if is_bug:
                first_col = self.bug_project.get_columns()[0]
            else:
                first_col = self.feature_project.get_columns()[0]

            first_col.create_card(content_id=issue_num, content_type="Issue")

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def get_or_create_branch(self, repo, branch, base):
        """Returns the branch named `branch` on repo, creating it from `base`'s current
        commit if it doesn't already exist."""
        if not isinstance(repo, Repository):
            repo = self.get_repo(repo)

        def _():
            try:
                return repo.get_branch(branch)
            except GithubException as e:
                if e.status != 404:
                    raise
                base_branch = repo.get_branch(base)
                repo.create_git_ref(ref=f"refs/heads/{branch}", sha=base_branch.commit.sha)
                return repo.get_branch(branch)

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def create_or_update_file(self, repo, branch, path, content, message):
        """Creates the file at `path` on `branch`, or updates it if it already exists."""
        if not isinstance(repo, Repository):
            repo = self.get_repo(repo)

        def _():
            # read-then-write (not atomic): serialize per-branch if concurrent resubmissions race here
            try:
                existing = repo.get_contents(path, ref=branch)
                return repo.update_file(path, message, content, existing.sha, branch=branch)
            except GithubException as e:
                if e.status != 404:
                    raise
                return repo.create_file(path, message, content, branch=branch)

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def create_draft_pr(self, repo, branch, base, title, body):
        """Opens a draft PR from `branch` into `base`."""
        if not isinstance(repo, Repository):
            repo = self.get_repo(repo)

        def _():
            return repo.create_pull(title=title, body=body, head=branch, base=base, draft=True)

        return await asyncio.get_event_loop().run_in_executor(None, _)

    async def find_open_pr_for_branch(self, repo, branch):
        """Returns the open PR whose head is `branch`, or None if no such PR exists."""
        if not isinstance(repo, Repository):
            repo = self.get_repo(repo)

        def _():
            head = f"{repo.owner.login}:{branch}"
            for pr in repo.get_pulls(state="open", head=head):
                if pr.head.ref == branch:
                    return pr
            return None

        return await asyncio.get_event_loop().run_in_executor(None, _)
