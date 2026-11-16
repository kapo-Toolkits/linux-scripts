"""All user-visible text, in one place: English (default) and Georgian. The window and the web app get their words from here
(the web app receives the table as JSON), so a message reads the same everywhere. Keys never contain text of their own:
placeholders are {name} and must be the same in both languages (a unit test checks this and that no key is missing)."""
LANGS = ("en", "ka")
DEFAULT = "en"

TEXT = {
    "en": {
        "app_title": "DevOps Toolbox",
        "app_subtitle": "Safe, click-based DevOps operations",
        "language": "Language", "theme": "Theme", "theme_light": "Light", "theme_dark": "Dark",
        "categories": "Categories",
        "cat_linux": "Linux Administration",
        # operations
        "op_ufw_status": "UFW rules", "op_ufw_status_desc": "Show the firewall's state and every configured rule.",
        "op_ufw_add": "UFW: open or block a port", "op_ufw_add_desc": "Add an allow, deny or reject rule for one port and protocol.",
        "op_ufw_delete": "UFW: delete a rule", "op_ufw_delete_desc": "Remove an existing rule for a port.",
        "p_port": "Port (1-65535)", "p_proto": "Protocol", "p_action": "Action", "p_comment": "Description (optional)",
        "p_action_filter": "Only rules with this action",
        "act_allow": "Allow", "act_deny": "Deny", "act_reject": "Reject", "act_limit": "Limit", "act_any": "Any",
        "act_delete": "Delete rule", "proto_any": "tcp + udp",
        # firewall panel
        "fw_title": "UFW Firewall Manager",
        "fw_state": "Firewall", "fw_active": "active", "fw_inactive": "inactive", "fw_unknown": "unknown",
        "fw_not_installed": "UFW is not installed. Install it first (Debian/Ubuntu: sudo apt install ufw).",
        "fw_policy": "Default policy: incoming {incoming}, outgoing {outgoing}",
        "fw_rules": "Configured rules", "fw_other": "Other rules (shown only; manage them in a terminal)",
        "fw_no_rules": "No simple rules are configured.", "fw_rules_not_loaded": "The rule list has not been loaded yet.",
        "fw_col_action": "Action", "fw_col_port": "Port", "fw_col_proto": "Protocol", "fw_col_comment": "Description",
        "btn_refresh": "Refresh rules", "btn_preview": "Preview", "btn_execute": "Execute", "btn_cancel": "Cancel",
        "btn_confirm": "Yes, change the firewall", "btn_delete_selected": "Delete selected rule…", "btn_clear_history": "Clear history",
        "btn_close": "Close",
        "no_reload_note": "No reload is needed: UFW applies the rule at once while the firewall is active. (`ufw reload` is only for edits of /etc/ufw files made by hand, so this tool never runs it.)",
        "off_note": "This tool never switches the firewall off or on. Allow SSH first, then enable it yourself in a terminal: sudo ufw enable.",
        # preview / confirm
        "pv_title": "Preview", "pv_command": "Command", "pv_exact": "Runs as", "pv_risk": "Risk", "pv_root": "Administrator password",
        "pv_root_yes": "required (a system dialog will ask)", "pv_root_no": "not required", "pv_nothing": "Nothing to run.",
        "pv_warnings": "Please note", "pv_what": "What happens",
        "risk_info": "reads only", "risk_low": "low", "risk_medium": "changes the system", "risk_high": "high: removes a rule or may lock you out",
        "confirm_title": "Confirm firewall change",
        "confirm_text": "This changes the system firewall configuration.\n\n{commands}\n\nDo you want to continue?",
        "confirm_delete_title": "Confirm rule deletion",
        "confirm_delete_text": "This DELETES a firewall rule:\n\n{commands}\n\nThe change takes effect immediately and cannot be undone automatically. Continue?",
        # explanations and warnings
        "explain_status": "Reads the configured rules with `ufw show added`.",
        "explain_add_now": "UFW applies this rule immediately while the firewall is active.",
        "explain_delete_now": "UFW removes the rule immediately.",
        "explain_no_reload": "`ufw reload` is not needed and is not run.",
        "warn_rules_unknown": "The rule list is not loaded, so duplicates could not be checked. Press 'Refresh rules' first.",
        "warn_inactive": "The firewall is inactive: the rule is saved and starts working when the firewall is enabled.",
        "warn_state_unknown": "The firewall state could not be read.",
        "warn_ssh_lockout": "Blocking TCP port {port} can cut off SSH access to this computer.",
        "warn_ssh_delete": "Deleting the rule that allows port {port} can cut off SSH access once the firewall is active.",
        "warn_several_rules": "{n} rules match and will all be deleted.",
        "blocked_duplicate": "This rule already exists ({rule}). Nothing to do.",
        "blocked_conflict": "A different rule already covers this port ({rule}). Delete it first, then add the new one.",
        "blocked_rules_unknown": "Load the rule list first (Refresh rules): deleting never guesses.",
        "blocked_no_such_rule": "No such rule ({rule}) in the configured list.",
        # results
        "res_title": "Result", "res_ok": "Success", "res_failed": "Failed", "res_refused": "Not executed",
        "res_exit": "Exit code", "res_output": "Output",
        "ok_status": "{n} rule(s) loaded.", "ok_rule_added": "The rule was added.", "ok_rule_exists": "The rule already existed; nothing changed.",
        "ok_rule_deleted": "The rule was deleted.",
        # errors
        "err_unknown_operation": "Unknown operation.", "err_bad_token": "The preview expired or does not match. Preview again.",
        "err_not_confirmed": "The operation was not confirmed.", "err_missing_param": "A required value is missing: {name}.",
        "err_unknown_param": "Unexpected value: {name}.",
        "err_port_invalid": "The port must be a whole number from {min} to {max}.", "err_port_range": "The port must be between {min} and {max}.",
        "err_choice": "Choose one of: {allowed}.", "err_protocol": "The protocol must be one of: {allowed}.",
        "err_action": "The action must be one of: {allowed}.",
        "err_comment_invalid": "The description may have at most {max} characters, no quotes, backslashes or control characters, and may not start with '-'.",
        "err_timeout": "The command took too long and was stopped.", "err_not_found": "The program could not be found.",
        "err_permission": "Permission denied.", "err_os": "The system could not run the command. {detail}",
        "err_no_pkexec": "Administrator rights need pkexec (package polkit), which is not installed. Run this operation in a terminal instead.",
        "err_not_authorized": "Administrator permission was refused or the password dialog was closed. Nothing was changed.",
        "err_ufw_missing": "UFW is not installed (Debian/Ubuntu: sudo apt install ufw).",
        "err_rule_missing": "UFW reported that the rule does not exist, so nothing was deleted.",
        "err_firewall_backend": "UFW could not talk to the firewall (iptables/nftables). Is the system's firewall available, and are you allowed to change it?",
        "err_ufw_failed": "UFW reported an error: {detail}",
        # history
        "hist_title": "History", "hist_time": "Time", "hist_operation": "Operation", "hist_status": "Status", "hist_exit": "Exit", "hist_summary": "Summary",
        "hist_empty": "Nothing has been run yet.", "hist_cleared": "History cleared.",
        "status_ready": "Ready.", "working": "Working… (a system dialog may ask for the administrator password)",
        "web_started": "Open {url} in your browser. Press Ctrl+C to stop.", "web_token_hint": "Local use only",
    },
    "ka": {
        "app_title": "DevOps ხელსაწყოები",
        "app_subtitle": "უსაფრთხო DevOps ოპერაციები ერთი დაჭერით",
        "language": "ენა", "theme": "თემა", "theme_light": "ღია", "theme_dark": "მუქი",
        "categories": "კატეგორიები",
        "cat_linux": "Linux-ის ადმინისტრირება",
        "op_ufw_status": "UFW-ის წესები", "op_ufw_status_desc": "აჩვენებს firewall-ის მდგომარეობას და ყველა გამართულ წესს.",
        "op_ufw_add": "UFW: პორტის გახსნა ან დაბლოკვა", "op_ufw_add_desc": "ამატებს allow, deny ან reject წესს ერთი პორტისა და პროტოკოლისთვის.",
        "op_ufw_delete": "UFW: წესის წაშლა", "op_ufw_delete_desc": "შლის პორტის არსებულ წესს.",
        "p_port": "პორტი (1-65535)", "p_proto": "პროტოკოლი", "p_action": "მოქმედება", "p_comment": "აღწერა (არასავალდებულო)",
        "p_action_filter": "მხოლოდ ამ მოქმედების წესები",
        "act_allow": "დაშვება", "act_deny": "აკრძალვა", "act_reject": "უარყოფა", "act_limit": "შეზღუდვა", "act_any": "ნებისმიერი",
        "act_delete": "წესის წაშლა", "proto_any": "tcp + udp",
        "fw_title": "UFW Firewall-ის მართვა",
        "fw_state": "Firewall", "fw_active": "ჩართულია", "fw_inactive": "გამორთულია", "fw_unknown": "უცნობია",
        "fw_not_installed": "UFW დაყენებული არ არის. ჯერ დააყენეთ (Debian/Ubuntu: sudo apt install ufw).",
        "fw_policy": "ნაგულისხმევი პოლიტიკა: შემომავალი {incoming}, გამავალი {outgoing}",
        "fw_rules": "გამართული წესები", "fw_other": "სხვა წესები (მხოლოდ ჩანს; მართეთ ტერმინალიდან)",
        "fw_no_rules": "მარტივი წესები არ არის გამართული.", "fw_rules_not_loaded": "წესების სია ჯერ არ ჩატვირთულა.",
        "fw_col_action": "მოქმედება", "fw_col_port": "პორტი", "fw_col_proto": "პროტოკოლი", "fw_col_comment": "აღწერა",
        "btn_refresh": "წესების განახლება", "btn_preview": "წინასწარი ნახვა", "btn_execute": "შესრულება", "btn_cancel": "გაუქმება",
        "btn_confirm": "დიახ, შევცვალო firewall", "btn_delete_selected": "არჩეული წესის წაშლა…", "btn_clear_history": "ისტორიის გასუფთავება",
        "btn_close": "დახურვა",
        "no_reload_note": "გადატვირთვა საჭირო არ არის: UFW წესს მაშინვე ამოქმედებს, სანამ firewall ჩართულია. (`ufw reload` საჭიროა მხოლოდ /etc/ufw-ის ფაილების ხელით შეცვლის შემდეგ, ამიტომ ეს ხელსაწყო მას არასდროს უშვებს.)",
        "off_note": "ეს ხელსაწყო firewall-ს არასდროს რთავს და არც თიშავს. ჯერ დაუშვით SSH, მერე თავად ჩართეთ ტერმინალიდან: sudo ufw enable.",
        "pv_title": "წინასწარი ნახვა", "pv_command": "ბრძანება", "pv_exact": "გაეშვება როგორც", "pv_risk": "რისკი", "pv_root": "ადმინისტრატორის პაროლი",
        "pv_root_yes": "საჭიროა (სისტემური ფანჯარა მოგთხოვთ)", "pv_root_no": "საჭირო არ არის", "pv_nothing": "გასაშვები არაფერია.",
        "pv_warnings": "გაითვალისწინეთ", "pv_what": "რა მოხდება",
        "risk_info": "მხოლოდ კითხულობს", "risk_low": "დაბალი", "risk_medium": "ცვლის სისტემას", "risk_high": "მაღალი: შლის წესს ან შეიძლება თავი ჩაიკეტოთ",
        "confirm_title": "Firewall-ის ცვლილების დადასტურება",
        "confirm_text": "ეს ცვლის სისტემის firewall-ის კონფიგურაციას.\n\n{commands}\n\nგსურთ გაგრძელება?",
        "confirm_delete_title": "წესის წაშლის დადასტურება",
        "confirm_delete_text": "ეს წაშლის firewall-ის წესს:\n\n{commands}\n\nცვლილება მაშინვე ძალაში შედის და ავტომატურად ვერ დაბრუნდება. გავაგრძელო?",
        "explain_status": "კითხულობს გამართულ წესებს ბრძანებით `ufw show added`.",
        "explain_add_now": "UFW ამ წესს მაშინვე ამოქმედებს, სანამ firewall ჩართულია.",
        "explain_delete_now": "UFW წესს მაშინვე შლის.",
        "explain_no_reload": "`ufw reload` საჭირო არ არის და არ გაეშვება.",
        "warn_rules_unknown": "წესების სია ჩატვირთული არ არის, ამიტომ დუბლიკატები ვერ შემოწმდა. ჯერ დააჭირეთ „წესების განახლებას“.",
        "warn_inactive": "Firewall გამორთულია: წესი შეინახება და იმუშავებს firewall-ის ჩართვის შემდეგ.",
        "warn_state_unknown": "Firewall-ის მდგომარეობის წაკითხვა ვერ მოხერხდა.",
        "warn_ssh_lockout": "TCP პორტის {port} დაბლოკვამ შეიძლება ამ კომპიუტერთან SSH წვდომა გაწყვიტოს.",
        "warn_ssh_delete": "პორტის {port} დამშვები წესის წაშლამ შეიძლება SSH წვდომა გაწყვიტოს, როცა firewall ჩაირთვება.",
        "warn_several_rules": "{n} წესი ემთხვევა და ყველა წაიშლება.",
        "blocked_duplicate": "ეს წესი უკვე არსებობს ({rule}). გასაკეთებელი არაფერია.",
        "blocked_conflict": "ამ პორტს უკვე სხვა წესი ფარავს ({rule}). ჯერ ის წაშალეთ, მერე დაამატეთ ახალი.",
        "blocked_rules_unknown": "ჯერ ჩატვირთეთ წესების სია (წესების განახლება): წაშლა არასდროს ვარაუდობს.",
        "blocked_no_such_rule": "ასეთი წესი ({rule}) გამართულ სიაში არ არის.",
        "res_title": "შედეგი", "res_ok": "წარმატება", "res_failed": "ჩავარდა", "res_refused": "არ შესრულებულა",
        "res_exit": "გასვლის კოდი", "res_output": "გამოტანა",
        "ok_status": "ჩაიტვირთა {n} წესი.", "ok_rule_added": "წესი დაემატა.", "ok_rule_exists": "წესი უკვე არსებობდა; არაფერი შეცვლილა.",
        "ok_rule_deleted": "წესი წაიშალა.",
        "err_unknown_operation": "უცნობი ოპერაცია.", "err_bad_token": "წინასწარი ნახვა ამოიწურა ან არ ემთხვევა. ნახეთ თავიდან.",
        "err_not_confirmed": "ოპერაცია არ დადასტურებულა.", "err_missing_param": "აუცილებელი მნიშვნელობა აკლია: {name}.",
        "err_unknown_param": "მოულოდნელი მნიშვნელობა: {name}.",
        "err_port_invalid": "პორტი უნდა იყოს მთელი რიცხვი {min}-დან {max}-მდე.", "err_port_range": "პორტი უნდა იყოს {min}-სა და {max}-ს შორის.",
        "err_choice": "აირჩიეთ ერთ-ერთი: {allowed}.", "err_protocol": "პროტოკოლი უნდა იყოს ერთ-ერთი: {allowed}.",
        "err_action": "მოქმედება უნდა იყოს ერთ-ერთი: {allowed}.",
        "err_comment_invalid": "აღწერა შეიძლება იყოს მაქსიმუმ {max} სიმბოლო, ბრჭყალების, უკანა ირიბი ხაზისა და მართვის სიმბოლოების გარეშე და არ უნდა იწყებოდეს '-'-ით.",
        "err_timeout": "ბრძანებას ძალიან დიდი დრო დასჭირდა და გაჩერდა.", "err_not_found": "პროგრამა ვერ მოიძებნა.",
        "err_permission": "წვდომა აკრძალულია.", "err_os": "სისტემამ ბრძანება ვერ გაუშვა. {detail}",
        "err_no_pkexec": "ადმინისტრატორის უფლებებისთვის საჭიროა pkexec (პაკეტი polkit), რომელიც დაყენებული არ არის. გაუშვით ეს ოპერაცია ტერმინალიდან.",
        "err_not_authorized": "ადმინისტრატორის ნებართვა უარყოფილია ან პაროლის ფანჯარა დაიხურა. არაფერი შეცვლილა.",
        "err_ufw_missing": "UFW დაყენებული არ არის (Debian/Ubuntu: sudo apt install ufw).",
        "err_rule_missing": "UFW-მა თქვა, რომ ასეთი წესი არ არსებობს, ამიტომ არაფერი წაშლილა.",
        "err_firewall_backend": "UFW-მ firewall-თან (iptables/nftables) კავშირი ვერ დაამყარა. ხომ არ არის სისტემის firewall მიუწვდომელი და გაქვთ თუ არა მისი შეცვლის უფლება?",
        "err_ufw_failed": "UFW-მა შეცდომა დააფიქსირა: {detail}",
        "hist_title": "ისტორია", "hist_time": "დრო", "hist_operation": "ოპერაცია", "hist_status": "სტატუსი", "hist_exit": "კოდი", "hist_summary": "მოკლედ",
        "hist_empty": "ჯერ არაფერი გაშვებულა.", "hist_cleared": "ისტორია გასუფთავდა.",
        "status_ready": "მზადაა.", "working": "მუშაობს… (სისტემურმა ფანჯარამ შეიძლება ადმინისტრატორის პაროლი მოგთხოვოთ)",
        "web_started": "გახსენით {url} ბრაუზერში. გასაჩერებლად დააჭირეთ Ctrl+C.", "web_token_hint": "მხოლოდ ლოკალური გამოყენებისთვის",
    },
}


def norm_lang(lang):
    return lang if lang in TEXT else DEFAULT


def t(lang, key, **kw):
    """The text for `key` in `lang` (English if the key is missing there, the key itself if it exists nowhere)."""
    text = TEXT[norm_lang(lang)].get(key)
    if text is None:
        text = TEXT[DEFAULT].get(key, key)
    try:
        return text.format(**kw) if kw else text
    except (KeyError, IndexError, ValueError):
        return text


def add(key, en, ka):
    """Register a text for both languages at once (used by the operation modules, so an operation can never exist in one language only)."""
    if key in TEXT["en"] and (TEXT["en"][key] != en or TEXT["ka"][key] != ka):
        raise ValueError("text key defined twice with different words: " + key)
    TEXT["en"][key], TEXT["ka"][key] = en, ka
    return key
