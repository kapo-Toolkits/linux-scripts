"""Operation modules. Importing this package registers every operation (see registry.py); the order here is the order of the
categories in the window: Network, Firewall, SSH, Services, Web, Docker, Git, Users, Updates, Disk, Monitoring, Security, Database, Backup."""
from . import ufw, network, ssh, services, webserver, docker, git, users, packages, disk, monitor, security, database, backup  # noqa: F401
