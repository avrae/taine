# taine
[![CodeFactor](https://www.codefactor.io/repository/github/avrae/taine/badge)](https://www.codefactor.io/repository/github/avrae/taine)
[![Build Status](https://travis-ci.org/avrae/taine.svg?branch=master)](https://travis-ci.org/avrae/taine)

Taine is the main bot to track Avrae bugs and feature requests in Discord.  

### How to contribute
Taine should be easy to run locally - as long as you're running Python 3.6+ and have set two environment variables - `TOKEN` and `GITHUB_TOKEN` - to a valid Discord bot token and a valid GitHub personal access token, respectively, you can just run `python bot.py` after you've configured the constants.

#### Constants
At the top of `bot.py`, there are some constants:
- TOKEN - The bot token, if you'd rather set it here.
- GITHUB_TOKEN - A GitHub Personal Access Token, to post bug reports on GitHub.
- GITHUB_REPO - The GitHub repository path to post issues on.
- OWNER_ID - The Discord User ID of the bot's owner. Used to check if a user can run owner-only commands.
- BUG_CHAN - The Discord Channel ID of the channel to listen for bug reports.
- DDB_CHAN - The Discord Channel ID of the channel to listen for D&D Beyond bug reports.
- FEATURE_CHAN - The Discord Channel ID of the channel to listen for feature requests.
- TRACKER_CHAN - The Discord Channel ID of the channel to post all generated reports.
- REACTIONS - A list of Unicode/Discord reactions that the bot will react to reports with.

All constants must be unique.

#### Pull Requests
I (zhu.exe#4211) try to review PRs in a timely manner. A good PR should be descriptive, unique, and useful. Additionally, code should be readable and conform to PEP-8 standards.
