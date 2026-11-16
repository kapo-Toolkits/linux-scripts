"""PostgreSQL (MyDevOps tasks 10, 11, 24 and 25): the databases, version, a few settings, the roles, and a backup with pg_dump. Reads run as the
`postgres` account through pkexec (like `sudo -u postgres psql`); the backup runs as you and uses ~/.pgpass, so no password is ever typed here."""
import os
import time

from . import _dsl
from ._dsl import P, op
from .. import i18n

C = "db"
_dsl.category(C, "Database (PostgreSQL)", "მონაცემთა ბაზა (PostgreSQL)")
SETTINGS = ("shared_buffers", "max_connections", "work_mem", "effective_cache_size", "maintenance_work_mem", "listen_addresses")
BACKUPS = "backups"                                    # ~/backups, created with mode 700
i18n.add("explain_pgpass", "The backup logs in with ~/.pgpass (mode 600): no password is typed here.", "ბექაპი ~/.pgpass-ით შედის (რეჟიმი 600): პაროლი აქ არ იწერება.")
i18n.add("explain_as_postgres", "Runs as the 'postgres' system account (like sudo -u postgres).", "ეშვება 'postgres' სისტემური ანგარიშით (როგორც sudo -u postgres).")
PG = [("explain_as_postgres", {})]

op("db.list", C, ("List databases", "მონაცემთა ბაზების სია"), ("Every database and its owner (psql -l).", "ყველა მონაცემთა ბაზა და მისი მფლობელი (psql -l)."), argv=["@psql", "-l"], root=True, as_user="postgres", explain=PG)
op("db.version", C, ("PostgreSQL version", "PostgreSQL-ის ვერსია"), ("The server version (SELECT version()).", "სერვერის ვერსია (SELECT version())."),
   argv=["@psql", "-c", "SELECT version();"], root=True, as_user="postgres", explain=PG)
op("db.show", C, ("Show a setting", "პარამეტრის ჩვენება"), ("The current value of a setting (SHOW name).", "პარამეტრის მიმდინარე მნიშვნელობა (SHOW name)."),
   build=lambda ctx, p: [["psql", "-c", "SHOW %s;" % p["setting"]]], params=[P("setting", "choice", choices=SETTINGS, default="shared_buffers")], root=True, as_user="postgres", explain=PG)
op("db.roles", C, ("List roles", "როლების სია"), ("Database roles and their attributes (\\du).", "მონაცემთა ბაზის როლები და მათი ატრიბუტები (\\du)."), argv=["@psql", "-c", "\\du"], root=True, as_user="postgres", explain=PG)


def _backup(ctx, p):
    d = os.path.join(ctx.sysx.home, BACKUPS)
    out = os.path.join(d, "%s_%s.sql" % (p["db"], time.strftime("%Y-%m-%d_%H-%M-%S")))
    return [["mkdir", "-p", "-m", "700", d], ["pg_dump", "-w", "-h", "localhost", "-U", p["dbuser"], "-d", p["db"], "-f", out]]


op("db.backup", C, ("Back up a database", "მონაცემთა ბაზის ბექაპი"), ("Writes a SQL dump to ~/backups (pg_dump -w -h localhost); needs ~/.pgpass for the login.", "SQL დამპს წერს ~/backups-ში (pg_dump -w -h localhost); შესასვლელად საჭიროა ~/.pgpass."),
   build=_backup, params=[P("dbuser", "identifier", label="user", default="postgres"), P("db", "identifier", default="postgres")], risk="low", timeout=600,
   explain=[("explain_pgpass", {})])
