"""Command line for qgis-installer: look, plan, install, list, uninstall - with a dry run and JSON.

    qgis-installer-cli info
    qgis-installer-cli recipes                                   # every way the guide describes, and which fit here
    qgis-installer-cli recommend --goal stable|latest|alongside  # the best one for this system, and why
    qgis-installer-cli plan [--goal G | --recipe ID | --method A|B|C] [--channel ltr] [--branch lts] [--script | --json]
    qgis-installer-cli install [same options] [--yes] [--dry-run]
    qgis-installer-cli list
    qgis-installer-cli instances                                 # every QGIS that can be started, with how
    qgis-installer-cli check-updates                             # is a newer build waiting? (reads only)
    qgis-installer-cli launch ID [--yes]                         # start that QGIS (ID from: instances)
    qgis-installer-cli versions ID                               # the versions that installation could be at
    qgis-installer-cli install-version ID VERSION [--yes] [--dry-run]    # go to one (also back to an older one)
    qgis-installer-cli hold ID | unhold ID [--yes] [--dry-run]   # keep the installed version / allow updates again
    qgis-installer-cli env export [--name TEXT] [--output FILE]  # write what this machine has as an environment file
    qgis-installer-cli env check FILE                            # how far is this machine from that file? (reads only)
    qgis-installer-cli env apply FILE [--yes] [--dry-run]        # install what is missing (commands shown, simulated, confirmed)
    qgis-installer-cli doctor                                    # look for what is known to break QGIS (reads only; exit 1 = a problem)
    qgis-installer-cli update [--yes] [--dry-run]                # newest build of the QGIS installations found here
    qgis-installer-cli uninstall [--kinds apt,repo,flatpak,snap,dist,data] [--purge] [--yes] [--dry-run]
    qgis-installer-cli components [list] [--category cli|engine|python|db]   # what can be added next to QGIS, and what is there
    qgis-installer-cli components install ID [ID...] [--yes] [--dry-run]
    qgis-installer-cli requirements check [--plugin postgis_manager]
    qgis-installer-cli requirements install --plugin postgis_manager [--optional] [--yes] [--dry-run]

Nothing runs without confirmation (``--yes`` or an interactive "y"). Exit codes: 0 ok, 1 a step
failed, 2 not possible here / bad arguments, 3 not confirmed.
Hidden helpers for tests and "what would this do on another system":
--os-release FILE --pm PM --arch ARCH --tools flatpak,distrobox --immutable ostree|transactional|none.
"""
import argparse
import json
import sys

from . import __version__, doctor, envspec, i18n, instances, plan, recipes, requirements, runner, simulate, system, uninstall, update, versions

SCHEMA = 1
KINDS = ("apt", "repo", "flatpak", "snap", "dist", "data")


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
        "methods": {m: system.method_available(m, sysinfo) for m in "ABC"},
        "channels": system.allowed_channels(sysinfo) if system.method_available("A", sysinfo) else [],
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


def _opts_from_args(args):
    opts = {"grass": not args.no_grass, "python": not args.no_python, "server": args.server}
    for key in ("channel", "branch", "scope", "image"):
        if getattr(args, key, None):
            opts[key] = getattr(args, key)
    if getattr(args, "geo_repo", False):
        opts["geo_repo"] = True
    return opts


def _install_plan(args, sysinfo, lang):
    """-> plan dict {recipe, steps, notes, manual, why?} or None after saying why not."""
    t = lambda k, **kw: i18n.t(k, lang, **kw)  # noqa: E731
    opts = _opts_from_args(args)
    if args.method == "C":                      # the old 'distribution package', exactly as before
        pkgs = {"grass": opts["grass"], "python": opts["python"], "server": opts["server"]}
        steps = plan.build_install("C", sysinfo, opts.get("channel") or system.default_channel(sysinfo), pkgs)
        return {"recipe": "distro", "steps": steps, "notes": [], "manual": []}
    rid, why = args.recipe or recipes.METHOD_TO_RECIPE.get(args.method or ""), None
    if rid is None:
        rec = recipes.recommend(sysinfo, args.goal)
        if rec["recipe"] is None:
            print(t("why_nothing_fits", url=recipes.GUIDE_URL), file=sys.stderr)
            return None
        rid, why = rec["recipe"], rec["why"]
        opts = dict(opts, **{k: v for k, v in rec["options"].items() if k not in opts})
    ok, reason = recipes.applicability(rid, sysinfo)
    if not ok:
        if args.method and not args.recipe:
            print("method {} is not available on this system".format(args.method), file=sys.stderr)
        else:
            print(t("rc_not_applicable", recipe=rid, why=t("rcn_" + reason)), file=sys.stderr)
        return None
    if rid == "apt-official" and opts.get("channel", system.default_channel(sysinfo)) not in system.allowed_channels(sysinfo):
        print("channel '{}' is not offered for this system (allowed: {})".format(
            opts["channel"], ", ".join(system.allowed_channels(sysinfo))), file=sys.stderr)
        return None
    try:
        result = recipes.make_plan(rid, sysinfo, opts)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return None
    result["why"] = why
    return result


def _recipe_doc(rid, lang):
    return {"id": rid, "title": i18n.t("rc_" + rid, lang), "kind": recipes.RECIPES[rid]["kind"],
            "verified": recipes.RECIPES[rid]["verified"],
            "verified_text": i18n.t("vf_" + recipes.RECIPES[rid]["verified"], lang)}


def _show_plan(result, args, lang):
    t = lambda k, **kw: i18n.t(k, lang, **kw)  # noqa: E731
    rid = result["recipe"]
    if rid == "distro":
        _show(result["steps"], args, lang, "install")
        return
    titles = {"update": "upd_title", "hold": "lock_title_on", "unhold": "lock_title_off", "install-version": "ver_title", "env-apply": "env_title"}
    doc = _recipe_doc(rid, lang) if rid not in titles else {
        "id": rid, "title": i18n.t(titles[rid], lang), "kind": "run", "verified": "guide",
        "verified_text": i18n.t("vf_guide", lang)}
    notes = [{"key": k, "text": t("rcw_" + k)} for k in result["notes"]]
    manual = [{"title": t("rcm_" + m["title"]), "text": m["text"]} for m in result["manual"]]
    if args.json:
        print(json.dumps(dict(doc, schema=SCHEMA, steps=result["steps"], notes=notes, manual=manual,
                              why=t("why_" + result["why"], url=recipes.GUIDE_URL) if result.get("why") else None),
                         indent=2, ensure_ascii=False))
        return
    if getattr(args, "script", False) and result["steps"]:
        print(plan.steps_script(result["steps"]))
        return
    print("{} [{}]".format(doc["title"], doc["verified_text"]))
    if result.get("why"):
        print(t("why_" + result["why"], url=recipes.GUIDE_URL))
    if result["steps"]:
        print()
        print(t("will_run"))
        print(i18n.steps_text(result["steps"], lang))
    for m in manual:
        print("\n# " + m["title"])
        print(m["text"])
    for n in notes:
        print("\n* " + n["text"])


def _instances_cmd(args, items, lang):
    t = lambda k, **kw: i18n.t(k, lang, **kw)  # noqa: E731
    rows = instances.list_instances(items)
    if args.cmd == "instances":
        for r in rows:
            r["locked"] = versions.lock_state(r["label_item"])                  # kept (True) / free (False) / not known (None)
    if args.cmd == "check-updates":
        res = {r["id"]: r for r in instances.check_updates(items)}
        for r in rows:
            r["updates"] = res.get(r["id"])
        if args.json:
            print(json.dumps({"schema": SCHEMA, "instances": [dict(r, label=i18n.label_for(r["label_item"], lang)) for r in rows]},
                             indent=2, ensure_ascii=False, default=str))
            return 0
        if not rows:
            print(t("inst_none"))
        for r in rows:
            u = r["updates"]
            state = {True: t("upd_available"), False: t("upd_current"), None: t("upd_unknown")}[u["update"] if u else None]
            extra = (" ({})".format(u["candidate"]) if u and u.get("candidate") and u["update"] else "")
            src = " - " + t("upd_" + u["source"]) if u else ""
            print("- {}: {}{}{}".format(i18n.label_for(r["label_item"], lang), state, extra, src))
        return 0
    if args.cmd == "instances":
        if args.json:
            print(json.dumps({"schema": SCHEMA, "instances": [dict(r, label=i18n.label_for(r["label_item"], lang)) for r in rows]},
                             indent=2, ensure_ascii=False))
            return 0
        if not rows:
            print(t("inst_none"))
        for r in rows:
            how = " ".join(r["launch"]) if r["launch"] else t("inst_cannot_launch")
            kept = " " + t("lock_marker") if r.get("locked") else ""
            print("- {}  [{}]{}\n    {}".format(i18n.label_for(r["label_item"], lang), r["id"], kept, how))
        return 0
    row = instances.find(rows, args.id)
    if row is None:
        print(t("inst_unknown_id", id=args.id, known=", ".join(r["id"] for r in rows) or "-"), file=sys.stderr)
        return 2
    if not row["launch"]:
        print(t("inst_cannot_launch"), file=sys.stderr)
        return 2
    print(i18n.label_for(row["label_item"], lang))
    print("  " + " ".join(row["launch"]))
    if row["shared_profile"]:
        print("* " + t("inst_profile"))
    if not args.yes:
        if not sys.stdin.isatty():
            print("not confirmed: pass --yes to start it without a prompt", file=sys.stderr)
            return 3
        if input(t("run") + "? [y/N] ").strip().lower() not in ("y", "yes"):
            print(t("cancel"))
            return 1
    print(t("inst_started", pid=instances.launch(row)))
    return 0


def _versions_cmd(args, items, lang):
    t = lambda k, **kw: i18n.t(k, lang, **kw)  # noqa: E731
    rows = instances.list_instances(items)
    row = instances.find(rows, args.id)
    if row is None:
        print(t("inst_unknown_id", id=args.id, known=", ".join(r["id"] for r in rows) or "-"), file=sys.stderr)
        return 2
    item, label = row["label_item"], i18n.label_for(row["label_item"], lang)
    if args.cmd in ("hold", "unhold"):
        result = versions.lock_steps(item, args.cmd == "hold")
        result["recipe"] = args.cmd
        _show_plan(dict(result, why=None), args, lang)
        return _execute(result["steps"], args, lang)
    found = versions.available(item)
    if args.cmd == "versions":
        if args.json:
            print(json.dumps({"schema": SCHEMA, "id": row["id"], "label": label, "locked": versions.lock_state(item), "versions": found["versions"],
                              "note": t("rcw_" + found["note"]) if found["note"] else None}, indent=2, ensure_ascii=False))
            return 0
        print(t("ver_head", label=label))
        for v in found["versions"]:
            print("  {}  {}  [{}]".format(v["version"], t("ver_installed") if v["installed"] else "", v["origin"]).replace("    [", "  ["))
        if not found["versions"]:
            print("  " + t("ver_none"))
        lock = versions.lock_state(item)
        print("  " + {True: t("lock_kept"), False: t("lock_free"), None: t("lock_unknown")}[lock])
        if found["note"]:
            print("* " + t("rcw_" + found["note"]))
        return 0
    row_v = next((v for v in found["versions"] if v["version"] == args.version), None)
    if row_v is None:
        print(t("ver_unknown_version", v=args.version, known=", ".join(v["version"] for v in found["versions"]) or "-"), file=sys.stderr)
        return 2
    try:
        result = versions.steps_for(item, row_v)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    result["recipe"] = "install-version"
    result["manual"] = []
    _show_plan(dict(result, why=None), args, lang)
    return _execute(result["steps"], args, lang)


def _doctor_cmd(args, sysinfo, items, lang):
    result = doctor.run_all(items, sysinfo)
    if args.json:
        print(json.dumps(dict(result, schema=SCHEMA), indent=2, ensure_ascii=False))
    else:
        print("\n".join(doctor.lines(result, lang)))
    return 1 if doctor.has_problem(result) else 0


def _read_spec(path, lang):
    """-> the validated spec, or None after saying why not (the file is untrusted)."""
    t = lambda k, **kw: i18n.t(k, lang, **kw)  # noqa: E731
    try:
        return envspec.load(path)
    except OSError as exc:
        print(t("env_unreadable", path=path, why=str(exc)), file=sys.stderr)
    except envspec.SpecError as exc:
        print(t("env_too_big") if "larger than 64 KB" in str(exc) else t("env_invalid", why=str(exc)), file=sys.stderr)
    return None


def _env_cmd(args, sysinfo, items, lang):
    t = lambda k, **kw: i18n.t(k, lang, **kw)  # noqa: E731
    rows = requirements.components(sysinfo["pm"])
    if args.env_cmd == "export":
        text = json.dumps(envspec.export_spec(items, rows, args.name), indent=2, ensure_ascii=False) + "\n"
        if args.output:
            try:
                with open(args.output, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(text)
            except OSError as exc:
                print(t("env_unreadable", path=args.output, why=str(exc)), file=sys.stderr)
                return 2
            print(t("env_written", path=args.output))
        else:
            sys.stdout.write(text)
        return 0
    spec = _read_spec(args.file, lang)
    if spec is None:
        return 2
    state = envspec.check(spec, items, rows)
    if args.env_cmd == "check" or not args.json:
        lines = envspec.describe(spec, state, lang)
        if args.env_cmd == "check":
            if args.json:
                print(json.dumps(dict(state, schema=SCHEMA), indent=2, ensure_ascii=False))
                return 0
            print("\n".join(lines))
            return 0 if not (state["components_missing"] or state["qgis"]["state"] == "missing") else 1
        print("\n".join(lines) + "\n")
    result = envspec.plan(spec, items, rows, sysinfo)
    if not result["steps"] and not result["manual"]:
        print(t("env_matches") if not result["notes"] else "\n".join("* " + t("rcw_" + n) for n in result["notes"]))
        return 0
    result["recipe"] = "env-apply"
    _show_plan(dict(result, why=None), args, lang)
    return _execute(result["steps"], args, lang)


def _update_cmd(args, sysinfo, items, lang):
    result = update.plan(items, sysinfo)
    result["recipe"] = "update"
    _show_plan(result, args, lang)
    return _execute(result["steps"], args, lang) if result["steps"] else 0


def _recipes_cmd(args, sysinfo, lang):
    rows = []
    for a in recipes.available(sysinfo):
        rows.append(dict(_recipe_doc(a["id"], lang), applies=a["applies"], reason=a["reason"],
                         reason_text=i18n.t("rcn_" + a["reason"], lang) if a["reason"] else ""))
    if args.json:
        print(json.dumps({"schema": SCHEMA, "recipes": rows}, indent=2, ensure_ascii=False))
        return 0
    for r in rows:
        if r["applies"]:
            print("[yes] {}  ({})".format(r["title"], r["verified_text"]))
        else:
            print("[no ] {}  - {}".format(r["title"], r["reason_text"]))
    return 0


def _recommend_cmd(args, sysinfo, lang):
    rec = recipes.recommend(sysinfo, args.goal)
    if args.json:
        doc = dict(rec, schema=SCHEMA, goal=args.goal,
                   why_text=i18n.t("why_" + rec["why"], lang, url=recipes.GUIDE_URL))
        if rec["recipe"]:
            doc["recipe_info"] = _recipe_doc(rec["recipe"], lang)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        return 0
    print("{}: {}".format(i18n.t("goal_" + args.goal, lang),
                          i18n.t("rc_" + rec["recipe"], lang) if rec["recipe"] else "-"))
    print(i18n.t("why_" + rec["why"], lang, url=recipes.GUIDE_URL))
    if rec["alternatives"]:
        print("also possible: " + ", ".join(i18n.t("rc_" + r, lang) for r in rec["alternatives"]))
    return 0 if rec["recipe"] else 2


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
    if steps and not args.json and not getattr(args, "no_simulate", False):
        text = simulate.format_text(simulate.explain(steps), lang)
        if text:
            print(text + "\n")
    if not steps:
        print(i18n.t("rc_manual_only", lang))
        return 0
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


def _components(args, sysinfo, lang):
    """components list / install: GDAL, PROJ, GRASS, SAGA, Python libraries, database clients - with the system's package manager."""
    t = lambda k, **kw: i18n.t(k, lang, **kw)  # noqa: E731
    pm = sysinfo["pm"]
    rows = requirements.components(pm)
    if getattr(args, "comp_cmd", None) == "install":
        ids = []
        for rid in args.ids:
            if rid not in requirements.REQ or "cat" not in requirements.REQ[rid]:
                print(t("cp_unknown", id=rid, known=", ".join(r["id"] for r in rows)), file=sys.stderr)
                return 2
            ids.append(rid)
        todo = [r["id"] for r in rows if r["id"] in ids and not r["present"]]
        for r in rows:
            if r["id"] in ids and r["present"]:
                print(t("cp_have", name=r["label"][lang]))
        if not todo:
            return 0
        if not pm:
            print(t("cp_no_pm"), file=sys.stderr)
            return 2
        steps, manual = requirements.install_steps(todo, pm)
        for rid in manual:
            print(t("rq_manual", name=requirements.REQ[rid]["label"][lang]), file=sys.stderr)
        if not steps:
            return 2
        _show(steps, args, lang, "components")
        return _execute(steps, args, lang)
    if args.category:
        rows = [r for r in rows if r["cat"] == args.category]
    if args.json:
        print(json.dumps({"schema": SCHEMA, "package_manager": pm, "components": rows}, indent=2, ensure_ascii=False))
        return 0
    for cat in requirements.CATEGORIES:
        part = [r for r in rows if r["cat"] == cat]
        if not part:
            continue
        print(t("cat_" + cat))
        for r in part:
            how = ""
            if not r["present"]:
                how = "  -> " + (" ".join(r["packages"]) if r["packages"] else t("rq_manual", name=r["label"][lang]))
            print("  [{}] {:12s} {}{}".format("x" if r["present"] else " ", r["id"], r["label"][lang], how))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="qgis-installer-cli", description=__doc__.split("\n\n")[0])
    ap.add_argument("--lang", choices=("en", "ka"), help="language of messages (default: the one the GUI remembers, else en)")
    ap.add_argument("--version", action="version", version="qgis-installer {}".format(__version__))
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--no-simulate", action="store_true", help="do not ask the package manager what the commands would do before they are shown")
    ap.add_argument("--os-release", help=argparse.SUPPRESS)
    ap.add_argument("--pm", help=argparse.SUPPRESS)
    ap.add_argument("--arch", help=argparse.SUPPRESS)
    ap.add_argument("--tools", help=argparse.SUPPRESS)
    ap.add_argument("--immutable", choices=("ostree", "transactional", "none"), help=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info", help="what this system is and what can be done here")
    sub.add_parser("recipes", help="every way the installation guide describes, and which ones fit this system")
    p = sub.add_parser("recommend", help="the best way for this system, and why")
    p.add_argument("--goal", choices=recipes.GOALS, default="stable")

    def install_opts(p):
        p.add_argument("--goal", choices=recipes.GOALS, default="stable",
                       help="what you want when you do not name a recipe (default: stable)")
        p.add_argument("--recipe", choices=list(recipes.RECIPES), help="a specific way to install (see: recipes)")
        p.add_argument("--method", choices=list("ABC"), help="old names: A official repository, B Flatpak, C distribution package")
        p.add_argument("--channel", choices=list(system.CHANNELS) + ["testing"],
                       help="official repository channel (AUR: ltr or testing; NixOS: ltr)")
        p.add_argument("--branch", choices=recipes.FLATPAK_BRANCHES, help="Flatpak branch: stable (QGIS 4) or lts (QGIS 3 LTR)")
        p.add_argument("--scope", choices=("user", "system"), help="Flatpak: for your user (default) or the whole system")
        p.add_argument("--geo-repo", action="store_true", help="openSUSE: also add the Application:Geo repository")
        p.add_argument("--image", help="container image for the distrobox / toolbx recipes")
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

    sub.add_parser("instances", help="every QGIS that can be started on this machine, and how")
    sub.add_parser("check-updates", help="is a newer build of each installation waiting? (reads only, installs nothing)")
    p = sub.add_parser("launch", help="start one installed QGIS (shows the command first)")
    p.add_argument("id", help="installation id, from: instances")
    p.add_argument("--yes", action="store_true", help="do not ask")
    p = sub.add_parser("versions", help="the versions an installation could be at (reads only)")
    p.add_argument("id", help="installation id, from: instances")
    p = sub.add_parser("install-version", help="go to a version of an installation (shows the commands and what they would do first)")
    p.add_argument("id")
    p.add_argument("version", help="a version from: versions ID")
    p.add_argument("--yes", action="store_true", help="do not ask")
    p.add_argument("--dry-run", action="store_true", help="only show the commands")
    for name, text in (("hold", "keep the installed version: no updates for it"), ("unhold", "allow updates for it again")):
        p = sub.add_parser(name, help=text)
        p.add_argument("id")
        p.add_argument("--yes", action="store_true", help="do not ask")
        p.add_argument("--dry-run", action="store_true", help="only show the commands")
    p = sub.add_parser("env", help="environment files: the same QGIS and components on many machines")
    es = p.add_subparsers(dest="env_cmd", required=True)
    q = es.add_parser("export", help="write what this machine has (QGIS, components) as an environment file")
    q.add_argument("--name", default="", help="a name for the file's content")
    q.add_argument("--output", help="the file to write (default: print it)")
    q = es.add_parser("check", help="how far is this machine from the file? (reads only)")
    q.add_argument("file")
    q = es.add_parser("apply", help="install what the file asks for and this machine lacks")
    q.add_argument("file")
    q.add_argument("--yes", action="store_true", help="do not ask")
    q.add_argument("--dry-run", action="store_true", help="only show the commands")
    sub.add_parser("doctor", help="look for what is known to break QGIS here (reads only)")
    p = sub.add_parser("update", help="update the QGIS installations found here (shows the commands first; close QGIS first)")
    p.add_argument("--yes", action="store_true", help="do not ask")
    p.add_argument("--dry-run", action="store_true", help="only show the commands")

    p = sub.add_parser("uninstall", help="remove QGIS installations (user data only when asked for)")
    p.add_argument("--kinds", help="comma separated: " + ",".join(KINDS) + " (default: all except data)")
    p.add_argument("--purge", action="store_true", help="also delete system configuration (apt purge)")
    p.add_argument("--no-autoremove", action="store_true")
    p.add_argument("--yes", action="store_true", help="do not ask")
    p.add_argument("--dry-run", action="store_true", help="only show the commands")
    p = sub.add_parser("components", help="GDAL, PROJ, GRASS, SAGA, Python libraries and database clients: what is there, what can be added")
    p.set_defaults(comp_cmd="list")
    p.add_argument("--category", choices=requirements.CATEGORIES, help="only this group")
    cs = p.add_subparsers(dest="comp_cmd")
    q = cs.add_parser("list", help="the components and whether each is present (default)")
    q.add_argument("--category", choices=requirements.CATEGORIES, help="only this group")
    q = cs.add_parser("install", help="install components with the system package manager (shows the commands first)")
    q.add_argument("ids", nargs="+", help="component ids, e.g. gdal numpy")
    q.add_argument("--yes", action="store_true", help="do not ask")
    q.add_argument("--dry-run", action="store_true", help="only show the commands")
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
    tools = None if args.tools is None else {t.strip(): True for t in args.tools.split(",") if t.strip()}
    immutable = args.immutable
    sysinfo = system.detect(args.os_release, args.pm, args.arch, tools=tools, immutable=immutable)

    if args.cmd == "info":
        return _info(args, sysinfo, lang)
    if args.cmd == "components":
        return _components(args, sysinfo, lang)
    if args.cmd == "requirements":
        return _requirements(args, sysinfo, lang)

    if args.cmd == "recipes":
        return _recipes_cmd(args, sysinfo, lang)
    if args.cmd == "recommend":
        return _recommend_cmd(args, sysinfo, lang)

    if args.cmd in ("plan", "install"):
        result = _install_plan(args, sysinfo, lang)
        if result is None:
            return 2
        _show_plan(result, args, lang)
        return 0 if args.cmd == "plan" else _execute(result["steps"], args, lang)

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

    if args.cmd == "update":
        return _update_cmd(args, sysinfo, items, lang)
    if args.cmd == "env":
        return _env_cmd(args, sysinfo, items, lang)
    if args.cmd == "doctor":
        return _doctor_cmd(args, sysinfo, items, lang)
    if args.cmd in ("instances", "check-updates", "launch"):
        return _instances_cmd(args, items, lang)
    if args.cmd in ("versions", "install-version", "hold", "unhold"):
        return _versions_cmd(args, items, lang)

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
