"""Command line for qgis-installer: look, plan, install, list, uninstall - with a dry run and JSON.

    qgis-installer-cli info
    qgis-installer-cli plan --method A --channel ltr [--server] [--script | --json]
    qgis-installer-cli install --method A --channel ltr [--yes] [--dry-run]
    qgis-installer-cli list
    qgis-installer-cli uninstall [--kinds apt,repo,flatpak,snap,dist,data] [--purge] [--yes] [--dry-run]
    qgis-installer-cli requirements check [--plugin postgis_manager]
    qgis-installer-cli requirements install --plugin postgis_manager [--optional] [--yes] [--dry-run]

Nothing runs without confirmation (``--yes`` or an interactive "y"). Exit codes: 0 ok, 1 a step
failed, 2 not possible here / bad arguments, 3 not confirmed.
Hidden helpers for tests and "what would this do on another system": --os-release FILE --pm PM --arch ARCH.
"""
import argparse
import json
import sys

from . import i18n, plan, requirements, runner, system, uninstall

SCHEMA = 1
KINDS = ("apt", "repo", "flatpak", "snap", "dist", "container", "data")


def _lang(arg):
    if arg in ("en", "ka"):
        return arg
    try:  # the language remembered by the GUI tools, when the shared helper is installed
        from lscommon import load_lang
        return load_lang()
    except Exception:  # noqa: BLE001
        return "en"


def _status_lines(sysinfo, lang):
    t = lambda k, **kw: i18n.t(k, lang, **kw)  # noqa: E731
    lines = [t("sys_line", name=sysinfo["name"], code=sysinfo["code"] or "-", arch=sysinfo["arch"],
               pm=sysinfo["pm"] or "-")]
    if not sysinfo["family"]:
        lines.append(t("st_nodeb"))
    elif not sysinfo["supported"]:
        lines.append(t("st_unsup"))
    else:
        lines.append(t("st_ltr") if sysinfo["ltr_only"] else t("st_ok"))
    if sysinfo["family"] and sysinfo["arch"] != "amd64":
        lines.append(t("st_arch"))
    return lines


def _info(args, sysinfo, lang):
    inst = system.installed_qgis()
    doc = {
        "schema": SCHEMA,
        "system": sysinfo,
        "installed_apt_version": inst,
        "methods": {m: system.method_available(m, sysinfo) for m in system.METHODS},
        "channels": system.allowed_channels(sysinfo) if system.method_available("A", sysinfo) else [],
        "method_channels": {m: system.channels_for(m, sysinfo) for m in system.METHODS
                            if system.method_available(m, sysinfo) and system.channels_for(m, sysinfo)},
        "default_channel": system.default_channel(sysinfo),
        "latest": system.LATEST,
        "ltr": system.LTR,
    }
    if args.json:
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        return 0
    print("\n".join(_status_lines(sysinfo, lang)))
    print(i18n.t("st_inst", lang, v=inst) if inst else i18n.t("st_none", lang))
    print("methods: " + ", ".join("{}={}".format(m, "yes" if ok else "no") for m, ok in doc["methods"].items()))
    if doc["channels"]:
        print("channels: " + ", ".join(doc["channels"]))
    return 0


def _install_steps(args, sysinfo):
    method = args.method or ("A" if system.method_available("A", sysinfo) else "B")
    if not system.method_available(method, sysinfo):
        print("method {} is not available on this system".format(method), file=sys.stderr)
        return None, None
    offered = system.channels_for(method, sysinfo)
    channel = args.channel or (system.default_channel(sysinfo) if method == "A" else "latest")
    if offered and channel not in offered:
        print("channel '{}' is not offered for method {} on this system (allowed: {})".format(
            channel, method, ", ".join(offered)), file=sys.stderr)
        return None, None
    pkgs = {"grass": not args.no_grass, "python": not args.no_python, "server": args.server}
    return method, plan.build_install(method, sysinfo, channel, pkgs)


def _show(steps, args, lang, title):
    if args.json:
        print(json.dumps({"schema": SCHEMA, "title": title, "steps": steps}, indent=2, ensure_ascii=False))
    elif getattr(args, "script", False):
        print(plan.steps_script(steps))
    else:
        print(i18n.t("will_run", lang))
        print(i18n.steps_text(steps, lang))


def _execute(steps, args, lang):
    """Confirm, run, report. Returns the exit code."""
    if args.dry_run:
        return 0
    if not args.yes:
        if not sys.stdin.isatty():
            print("not confirmed: pass --yes to run without a prompt", file=sys.stderr)
            return 3
        if input(i18n.t("run", lang) + "? [y/N] ").strip().lower() not in ("y", "yes"):
            print(i18n.t("cancel", lang))
            return 3
    rc, failed = runner.run_steps(steps, on_line=lambda s: print(s, end=""), elevate=runner.default_elevator())
    if rc == 0:
        print(i18n.t("done_ok", lang))
        return 0
    if runner.needs_elevation_fallback(rc, failed):
        path = runner.write_root_script(steps)
        print(i18n.t("elev_fail", lang, cmd="sudo sh " + path), file=sys.stderr)
    else:
        print(i18n.t("done_fail", lang, rc=rc), file=sys.stderr)
    return rc if rc else 1


def _requirements(args, sysinfo, lang):
    """requirements check / install: what the GIS GEORGIA plugins need from this system."""
    t = lambda k, **kw: i18n.t(k, lang, **kw)  # noqa: E731
    known = sorted(requirements.PLUGIN_REQUIREMENTS)
    plugins = [args.plugin] if args.plugin else known
    for p in plugins:
        if p not in requirements.PLUGIN_REQUIREMENTS:
            print(t("rq_unknown_plugin", plugin=p, known=", ".join(known)), file=sys.stderr)
            return 2
    pm = sysinfo["pm"]

    if args.rq_cmd == "check":
        doc = {"schema": SCHEMA, "package_manager": pm, "plugins": {}}
        for p in plugins:
            rows = []
            for r in requirements.status(p):
                pkgs, _ = requirements.packages_for([r["id"]], pm)
                rows.append(dict(r, packages=pkgs))
            doc["plugins"][p] = rows
        if args.json:
            print(json.dumps(doc, indent=2, ensure_ascii=False))
            return 0
        for p in plugins:
            print(t("rq_head", plugin=p))
            for r in doc["plugins"][p]:
                flag = t("rq_present") if r["present"] else t("rq_missing")
                opt = " (" + t("rq_optional") + ")" if r["optional"] else ""
                how = ""
                if not r["present"]:
                    how = "  -> " + (" ".join(r["packages"]) if r["packages"]
                                     else t("rq_manual", name=r["label"][lang]))
                print("  [{}] {}{}{}".format(flag, r["label"][lang], opt, how))
        return 0

    # install
    if not args.plugin:
        print("--plugin is required", file=sys.stderr)
        return 2
    rows = requirements.status(args.plugin)
    if not rows:
        print(t("rq_none", plugin=args.plugin))
        return 0
    wanted = [r["id"] for r in rows if not r["present"] and (args.optional or not r["optional"])]
    if not wanted:
        print(t("rq_all_ok"))
        return 0
    steps, manual = requirements.install_steps(wanted, pm)
    for rid in manual:
        print(t("rq_manual", name=requirements.REQ[rid]["label"][lang]), file=sys.stderr)
    if not steps:
        return 2
    _show(steps, args, lang, "requirements")
    return _execute(steps, args, lang)


def build_parser():
    ap = argparse.ArgumentParser(prog="qgis-installer-cli", description=__doc__.split("\n\n")[0])
    ap.add_argument("--lang", choices=("en", "ka"), help="language of messages (default: the one the GUI remembers, else en)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--os-release", help=argparse.SUPPRESS)
    ap.add_argument("--pm", help=argparse.SUPPRESS)
    ap.add_argument("--arch", help=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info", help="what this system is and what can be done here")

    def install_opts(p):
        p.add_argument("--method", choices=list(system.METHODS),
                       help="A official apt repository, B Flatpak, C distribution package, D container (Distrobox/Toolbx), E Nix")
        p.add_argument("--channel", choices=system.CHANNELS,
                       help="channel; see `info --json` method_channels for what each method offers")
        p.add_argument("--no-grass", action="store_true")
        p.add_argument("--no-python", action="store_true")
        p.add_argument("--server", action="store_true", help="also install qgis-server")

    p = sub.add_parser("plan", help="show the commands, run nothing")
    install_opts(p)
    p.add_argument("--script", action="store_true", help="print one POSIX shell script")

    p = sub.add_parser("install", help="install QGIS (shows the commands first)")
    install_opts(p)
    p.add_argument("--yes", action="store_true", help="do not ask")
    p.add_argument("--dry-run", action="store_true", help="only show the commands")

    sub.add_parser("list", help="every QGIS installation found on this machine")

    p = sub.add_parser("uninstall", help="remove QGIS installations (user data only when asked for)")
    p.add_argument("--kinds", help="comma separated: " + ",".join(KINDS) + " (default: all except data)")
    p.add_argument("--purge", action="store_true", help="also delete system configuration (apt purge)")
    p.add_argument("--no-autoremove", action="store_true")
    p.add_argument("--yes", action="store_true", help="do not ask")
    p.add_argument("--dry-run", action="store_true", help="only show the commands")
    p = sub.add_parser("requirements", help="what the GIS GEORGIA QGIS plugins need from this system")
    rq = p.add_subparsers(dest="rq_cmd", required=True)
    q = rq.add_parser("check", help="which requirements are present (this system's Python and PATH)")
    q.add_argument("--plugin", help="one plugin folder name (default: all)")
    q = rq.add_parser("install", help="install the missing ones with the system package manager")
    q.add_argument("--plugin", required=True, help="plugin folder name, e.g. postgis_manager")
    q.add_argument("--optional", action="store_true", help="also the optional ones")
    q.add_argument("--yes", action="store_true", help="do not ask")
    q.add_argument("--dry-run", action="store_true", help="only show the commands")
    return ap


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    lang = _lang(args.lang)
    sysinfo = system.detect(args.os_release, args.pm, args.arch)

    if args.cmd == "info":
        return _info(args, sysinfo, lang)
    if args.cmd == "requirements":
        return _requirements(args, sysinfo, lang)

    if args.cmd in ("plan", "install"):
        method, steps = _install_steps(args, sysinfo)
        if steps is None:
            return 2
        _show(steps, args, lang, "install")
        return 0 if args.cmd == "plan" else _execute(steps, args, lang)

    items = uninstall.find_installs(sysinfo)
    if args.cmd == "list":
        if args.json:
            print(json.dumps({"schema": SCHEMA, "items": items}, indent=2, ensure_ascii=False))
        elif not items:
            print(i18n.t("rm_none", lang))
        else:
            for it in items:
                print("- " + i18n.label_for(it, lang))
        return 0

    # uninstall
    if args.kinds:
        wanted = [k.strip() for k in args.kinds.split(",") if k.strip()]
        bad = [k for k in wanted if k not in KINDS]
        if bad:
            print("unknown kind(s): {} (choose from {})".format(", ".join(bad), ", ".join(KINDS)), file=sys.stderr)
            return 2
        chosen = [it for it in items if it["kind"] in wanted]
    else:
        chosen = uninstall.default_selection(items)
    steps = uninstall.build_remove_steps(chosen, args.purge, not args.no_autoremove, sysinfo)
    if not steps:
        print(i18n.t("rm_nothing", lang))
        return 0
    _show(steps, args, lang, "uninstall")
    return _execute(steps, args, lang)


if __name__ == "__main__":
    sys.exit(main())
