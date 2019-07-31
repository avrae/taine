# taine
[![Codacy Badge](https://api.codacy.com/project/badge/Grade/7c5174b6f97a4144b2c7a1a826f0bbee)](https://www.codacy.com/app/mommothazaz123/taine?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=avrae/taine&amp;utm_campaign=Badge_Grade)
[![Build Status](https://travis-ci.org/avrae/taine.svg?branch=master)](https://travis-ci.org/avrae/taine)

Taine is the main bot to track Avrae bugs and feature requests in Discord.  

## How it works
Taine is currently set to listen for issues on [avrae/avrae](https://github.com/avrae/avrae), [avrae/avrae.io](https://github.com/avrae/avrae.io), [avrae/avrae-service](https://github.com/avrae/avrae-service), and [avrae/taine](https://github.com/avrae/taine).
Whenever an issue is opened on any of those repositories, it follows this logic:
- Is the issue tagged with `enhancement`?
    - If so, the issue is an internal improvement. Taine does not track it.
- Is the issue tagged with `featurereq`?
    - If so, track the issue and copy it to Discord. Taine will set up a post in the tracker channel to allow users to vote on it.
- Is the issue tagged with `bug`, or untagged?
    - If so, track the issue as a bug and copy it to Discord.


## Requirements

- Python 3.6

## Configuration

Set the following environment variables:

- `DISCORD_TOKEN` - a Discord bot token.
- `GITHUB_TOKEN` - a Github Personal Access Token.
- `ORG_NAME` - name of the GitHub org your repos are in, defaults to `avrae`.

Other configuration is via `constants.py`:

- `OWNER_ID` - the Discord User ID of the bot's owner. Used to check if a user can run owner-only commands.
- `BUG_LISTEN_CHANS` - a list of dictionaries representing what channels to listen in, and the identifier and repo associated with that channel.
- `REPO_ID_MAP` - a dictionary defining what repos to listen for issues on, and the default identifier for issues opened on those repos.
- `TRACKER_CHAN` - the Discord Channel ID of the channel to post all generated reports.
- `OWNER_GITHUB` - issues closed by anyone other than this username will not be marked as pending for next patch.
- `MY_GITHUB` - the GitHub username of the bot.
- `REACTIONS` - a list of Unicode/Discord reactions that the bot will react to reports with.

All constants must be unique.

### Optional

These environment variables are optional:

- `FR_APPROVE_THRESHOLD` (default 5) - The minimum score for feature requests to be added to GitHub.
- `FR_DENY_THRESHOLD` (default -3) - The score for feature requests to be automatically closed if they fall under it.
- `NEW_RELIC_CONFIG_FILE` - Set to `newrelic.ini`.
- `NEW_RELIC_ENVIRONMENT` - Set to `development`, `staging`, or `production`.
- `NEW_RELIC_LICENSE_KEY` - License key for [New Relic](https://newrelic.com/).
- `SENTRY_DSN` - DSN for [Sentry](https://sentry.io/welcome/).

## Running the bot

1. Create a [virtual environment](https://docs.python.org/3/library/venv.html): `python3 -m venv venv`.
2. Activate the virtual environment: `source venv/bin/activate` on Unix (bash/zsh), `venv\Scripts\activate.bat` on Windows. You need to do this each time you open a new shell/command prompt.
3. Install the required Python packages: `pip install -r requirements.txt`.
4. Run the bot: `python bot.py`

## Pull Requests
I (zhu.exe#4211) try to review PRs in a timely manner. A good PR should be descriptive, unique, and useful. Additionally, code should be readable and conform to PEP-8 standards.
