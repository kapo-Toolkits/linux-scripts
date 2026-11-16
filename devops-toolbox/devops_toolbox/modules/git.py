"""Git (MyDevOps tasks 9, 18 and 19): your identity settings, and for the repositories YOU list in ~/.config/linux-scripts/devops-toolbox.json:
status, log, branches, remotes, changes, fetch, fast-forward pull, the current commit. (Committing, pushing and `reset --hard` are not
here: they decide what your project contains, so they stay in your hands.)"""
from . import _dsl
from ._dsl import P, grep, op
from .. import i18n

C = "git"
_dsl.category(C, "Git", "Git")
i18n.add("explain_git_repo", "The repository folder comes from your configuration file, never from a request.", "რეპოზიტორიის საქაღალდე თქვენი კონფიგურაციის ფაილიდან მოდის და არასოდეს მოთხოვნიდან.")
GR = [("explain_git_repo", {})]


@_dsl.dynamic("git_repos")
def _repos(ctx):
    return [x["name"] for x in _dsl.configured(ctx, "repos")]


def _path(ctx, name):
    return next(x["path"] for x in _dsl.configured(ctx, "repos") if x["name"] == name)


def repo_op(key, sub, en, ka, den, dka, risk="info", extra_params=(), post=None, timeout=60):
    def build(ctx, p):
        return [["git", "-C", _path(ctx, p["repo"])] + [x.format(**p) if "{" in x else x for x in sub]]
    op("git." + key, C, (en, ka), (den, dka), build=build, params=[P("repo", "choice", choices=(), dynamic="git_repos")] + list(extra_params),
       risk=risk, explain=GR, post=post, timeout=timeout)


repo_op("status", ["status", "-sb"], "Repository status", "რეპოზიტორიის სტატუსი", "Branch and changed files, short form (git status -sb).", "ბრენჩი და შეცვლილი ფაილები, მოკლედ (git status -sb).")
repo_op("log", ["log", "--oneline", "-n", "{lines}"], "Recent commits", "ბოლო კომიტები", "The latest commits, one line each (git log --oneline -n N).", "ბოლო კომიტები, თითო ხაზზე (git log --oneline -n N).",
        extra_params=[P("lines", lo=1, hi=100, default=10)])
repo_op("branch", ["branch", "-vv"], "Branches", "ბრენჩები", "Local branches and what they track (git branch -vv).", "ლოკალური ბრენჩები და რას მიჰყვებიან (git branch -vv).")
repo_op("remote", ["remote", "-v"], "Remotes", "დაშორებული რეპოზიტორიები", "Where the repository fetches from and pushes to (git remote -v).", "საიდან იღებს და სად უშვებს რეპოზიტორია (git remote -v).")
repo_op("diff", ["diff", "--stat"], "Changes (summary)", "ცვლილებები (შეჯამება)", "Which files changed and by how much (git diff --stat).", "რომელი ფაილები შეიცვალა და რამდენით (git diff --stat).")
repo_op("head", ["rev-parse", "HEAD"], "Current commit", "მიმდინარე კომიტი", "The id of the commit you are on (git rev-parse HEAD).", "კომიტის id, რომელზეც ხართ (git rev-parse HEAD).")
repo_op("files", ["ls-files"], "Tracked files", "თვალყურმდევნელი ფაილები", "The files git tracks, first 200 (git ls-files).", "ფაილები, რომლებსაც git აკონტროლებს, პირველი 200 (git ls-files).", post=lambda t: "\n".join(t.splitlines()[:200]))
repo_op("fetch", ["fetch", "--quiet"], "Fetch from the remote", "ცვლილებების წამოღება", "Downloads new commits without changing your files (git fetch).", "ჩამოტვირთავს ახალ კომიტებს თქვენი ფაილების შეცვლის გარეშე (git fetch).", risk="low", timeout=120)
repo_op("pull", ["pull", "--ff-only"], "Pull (fast-forward only)", "Pull (მხოლოდ fast-forward)", "Brings the branch up to date; refuses if it would need a merge (git pull --ff-only).", "ბრენჩს განაახლებს; თუ merge დასჭირდება, უარს იტყვის (git pull --ff-only).", risk="medium", timeout=180)

op("git.config.show", C, ("Git identity", "Git-ის იდენტობა"), ("Your global user.name, user.email and default branch (git config --global --list, filtered).", "თქვენი გლობალური user.name, user.email და ნაგულისხმევი ბრენჩი (git config --global --list, გაფილტრული)."),
   argv=["@git", "config", "--global", "--list"], post=grep("user.name=", "user.email=", "init.defaultbranch="), ok_codes=(0, 128))
op("git.config.set", C, ("Set a git identity value", "Git-ის იდენტობის მნიშვნელობის დაყენება"), ("Sets user.name, user.email or init.defaultBranch for you (git config --global).", "გიყენებთ user.name-ს, user.email-ს ან init.defaultBranch-ს (git config --global)."),
   argv=["@git", "config", "--global", "{key}", "{value}"], params=[P("key", "choice", choices=("user.name", "user.email", "init.defaultBranch"), default="user.name"), P("value")], risk="low")
