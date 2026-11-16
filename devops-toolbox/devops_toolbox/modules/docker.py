"""Docker (MyDevOps tasks 14, 15, 16, 19 and 21): versions, containers, images, resource use, disk use, logs, restart, remove an image,
prune, and Compose for the projects YOU list in ~/.config/linux-scripts/devops-toolbox.json (a project is chosen by name; its folder
comes from that file, never from a request)."""
from . import _dsl
from ._dsl import P, op
from .. import i18n

C = "docker"
_dsl.category(C, "Docker", "Docker")
i18n.add("explain_docker_group", "Docker runs as you: your account must be in the docker group (or run it with administrator rights in a terminal).",
         "Docker ეშვება თქვენი სახელით: თქვენი ანგარიში docker ჯგუფში უნდა იყოს (ან გაუშვით ადმინისტრატორის უფლებით ტერმინალიდან).")
i18n.add("warn_volumes_deleted", "This also deletes the project's volumes, including its database files.", "ეს პროექტის volume-ებსაც წაშლის, მათ შორის მონაცემთა ბაზის ფაილებს.")
i18n.add("warn_prune_all", "Removes every stopped container, unused network and every image that no container uses. Images are downloaded again when needed.",
         "შლის ყველა გაჩერებულ კონტეინერს, გამოუყენებელ ქსელს და ყველა იმიჯს, რომელსაც კონტეინერი არ იყენებს. იმიჯები საჭიროებისას თავიდან ჩამოიტვირთება.")
G = [("explain_docker_group", {})]


@_dsl.dynamic("compose_projects")
def _projects(ctx):
    return [x["name"] for x in _configured(ctx, "projects")]


_configured = _dsl.configured


def project_path(ctx, name):
    return next(x["path"] for x in _configured(ctx, "projects") if x["name"] == name)


op("dk.version", C, ("Docker versions", "Docker-ის ვერსიები"), ("Docker and Compose versions (docker --version, docker compose version).", "Docker-ისა და Compose-ის ვერსიები (docker --version, docker compose version)."),
   build=lambda ctx, p: [["docker", "--version"], ["docker", "compose", "version"]], explain=G)
op("dk.ps", C, ("Running containers", "გაშვებული კონტეინერები"), ("Containers that are running (docker ps).", "კონტეინერები, რომლებიც მუშაობს (docker ps)."), argv=["@docker", "ps"], explain=G)
op("dk.ps.all", C, ("All containers", "ყველა კონტეინერი"), ("Running and stopped containers (docker ps -a).", "გაშვებული და გაჩერებული კონტეინერები (docker ps -a)."), argv=["@docker", "ps", "-a"], explain=G)
op("dk.images", C, ("Images", "იმიჯები"), ("Downloaded images and their sizes (docker images).", "ჩამოტვირთული იმიჯები და მათი ზომები (docker images)."), argv=["@docker", "images"], explain=G)
op("dk.stats", C, ("Resource use", "რესურსების გამოყენება"), ("CPU and memory of each container, once (docker stats --no-stream).", "თითო კონტეინერის CPU და მეხსიერება, ერთხელ (docker stats --no-stream)."), argv=["@docker", "stats", "--no-stream"], explain=G, timeout=40)
op("dk.df", C, ("Docker disk use", "Docker-ის დისკის გამოყენება"), ("How much space images, containers and volumes use (docker system df).", "რამდენ ადგილს იკავებს იმიჯები, კონტეინერები და volume-ები (docker system df)."), argv=["@docker", "system", "df"], explain=G)
op("dk.logs", C, ("Container log", "კონტეინერის ჟურნალი"), ("The last lines a container wrote (docker logs --tail N).", "ბოლო ხაზები, რომლებიც კონტეინერმა დაწერა (docker logs --tail N)."),
   argv=["@docker", "logs", "--tail", "{lines}", "{container}"], params=[P("container", "identifier"), P("lines", lo=10, hi=500, default=50)], explain=G)
op("dk.restart", C, ("Restart a container", "კონტეინერის გადატვირთვა"), ("Restarts one container (docker restart).", "ერთ კონტეინერს ხელახლა უშვებს (docker restart)."),
   argv=["@docker", "restart", "{container}"], params=[P("container", "identifier")], risk="medium", explain=G)
op("dk.hello", C, ("Docker test run", "Docker-ის სატესტო გაშვება"), ("Runs the tiny hello-world image to prove Docker works (docker run --rm hello-world); downloads it the first time.", "უშვებს პატარა hello-world იმიჯს, რომ დადასტურდეს Docker-ის მუშაობა (docker run --rm hello-world); პირველად ჩამოტვირთავს."),
   argv=["@docker", "run", "--rm", "hello-world"], risk="low", explain=G, timeout=180)
op("dk.rmi", C, ("Remove an image", "იმიჯის წაშლა"), ("Deletes one downloaded image (docker rmi).", "შლის ერთ ჩამოტვირთულ იმიჯს (docker rmi)."),
   argv=["@docker", "rmi", "{image_ref}"], params=[P("image_ref", "image")], risk="high", explain=G)
op("dk.prune", C, ("Clean up Docker", "Docker-ის გასუფთავება"), ("Removes stopped containers, unused networks and unused images (docker system prune -a -f).", "შლის გაჩერებულ კონტეინერებს, გამოუყენებელ ქსელებსა და იმიჯებს (docker system prune -a -f)."),
   argv=["@docker", "system", "prune", "-a", "-f"], risk="high", warn=lambda ctx, p: [("warn_prune_all", {})], explain=G, timeout=300)


def compose(key, sub, label_en, label_ka, desc_en, desc_ka, extra=(), risk="info", lines=False, warn=None, timeout=120):
    params = [P("project", "choice", choices=(), dynamic="compose_projects")] + ([P("lines", lo=10, hi=500, default=50)] if lines else [])

    def build(ctx, p):
        tail = ["--tail", str(p["lines"])] if lines else []
        return [["docker", "compose", "--project-directory", project_path(ctx, p["project"])] + list(sub) + tail + list(extra)]
    op("dk.compose." + key, C, (label_en, label_ka), (desc_en, desc_ka), build=build, params=params,
       risk=risk, warn=warn, explain=G, timeout=timeout)


compose("ps", ("ps",), "Compose: status", "Compose: სტატუსი", "The services of one of your Compose projects (docker compose ps).", "თქვენი Compose პროექტის სერვისები (docker compose ps).")
compose("logs", ("logs",), "Compose: logs", "Compose: ჟურნალი", "The latest log lines of a project (docker compose logs --tail N).", "პროექტის ბოლო ჟურნალის ხაზები (docker compose logs --tail N).", lines=True)
compose("up", ("up", "-d"), "Compose: start", "Compose: გაშვება", "Starts the project in the background (docker compose up -d).", "პროექტს ფონზე უშვებს (docker compose up -d).", risk="medium")
compose("pull", ("pull",), "Compose: pull images", "Compose: იმიჯების განახლება", "Downloads newer images for the project (docker compose pull).", "პროექტისთვის უფრო ახალ იმიჯებს ჩამოტვირთავს (docker compose pull).", risk="low", timeout=600)
compose("restart", ("restart",), "Compose: restart", "Compose: გადატვირთვა", "Restarts the project's services (docker compose restart).", "პროექტის სერვისებს ხელახლა უშვებს (docker compose restart).", risk="medium")
compose("down", ("down",), "Compose: stop and remove containers", "Compose: გაჩერება და კონტეინერების წაშლა", "Stops the project and removes its containers; volumes (your data) are kept (docker compose down).", "აჩერებს პროექტს და შლის კონტეინერებს; volume-ები (თქვენი მონაცემები) რჩება (docker compose down).", risk="medium")
compose("rebuild", ("up", "-d", "--build", "--remove-orphans"), "Compose: rebuild and start", "Compose: აწყობა და გაშვება", "Rebuilds the images and starts the project (docker compose up -d --build --remove-orphans).", "ხელახლა აგებს იმიჯებს და პროექტს უშვებს (docker compose up -d --build --remove-orphans).", risk="medium", timeout=900)
compose("down_volumes", ("down", "-v"), "Compose: stop and DELETE volumes", "Compose: გაჩერება და volume-ების წაშლა", "Stops the project and deletes its containers AND volumes (docker compose down -v).", "აჩერებს პროექტს და შლის კონტეინერებს და volume-ებს (docker compose down -v).", risk="high",
        warn=lambda ctx, p: [("warn_volumes_deleted", {})])
