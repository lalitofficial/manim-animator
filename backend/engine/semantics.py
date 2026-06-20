"""Semantic, domain-aware concept resolution (the "attention" layer).

The Story names plain nouns — "cloud", "server", "database". Whether "cloud" means a
sky cloud or a cloud-service icon, and whether "server" can be drawn at all, depends on
the lesson's DOMAIN. This module:

1. infers a domain from the topic (deterministic keyword cues),
2. indexes the published imported icons by their clean titles, tagged with the domain of
   their source set (Azure/AWS/… → cloud-computing), and
3. resolves a plain concept to the best concrete asset id FOR THAT DOMAIN — rewriting
   "server" → a published server icon, or forcing "cloud" → a cloud-service icon in a
   cloud lesson, while leaving "tree"/"sun" as their cartoon recipes.

It rewrites the concept STRING before drawing, so `drawing.measure` resolves the concrete
id normally (cartoon recipe or the published rung) — no resolution/cache changes needed.
Hermetic + deterministic; when no candidates are published it is a no-op.
"""

from __future__ import annotations

from dataclasses import dataclass


# --------------------------------------------------------------------------- #
# Domain registry — cues (topic → domain), member sets, and forced overrides.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Domain:
    id: str
    cues: tuple[str, ...]  # topic keywords that select this domain
    sets: tuple[str, ...]  # tokens that match an imported set/library name
    force: tuple[str, ...]  # terms to override even if a cartoon asset exists (cloud→tech)


DOMAINS: tuple[Domain, ...] = (
    Domain(
        "cloud-computing",
        cues=(
            # NOTE: bare "cloud" is intentionally NOT a cue — "types of clouds" is weather,
            # not computing. Tech is signalled by provider/infra terms or "cloud computing".
            "azure",
            "aws",
            "gcp",
            "google cloud",
            "serverless",
            "kubernetes",
            "docker",
            "container",
            "devops",
            "saas",
            "paas",
            "iaas",
            "datacenter",
            "data center",
            "virtual machine",
            "load balancer",
            "microservice",
            "cdn",
            "s3",
            "ec2",
            "lambda",
            "vpc",
            "infrastructure as",
            "deployment",
            "cloud computing",
            "cloud service",
            "web service",
            "data center",
            "hosting",
        ),
        sets=(
            "azure",
            "aws",
            "gcp",
            "google cloud",
            "cloud",
            "kubernetes",
            "k8s",
            "docker",
            "oracle cloud",
            "cisco",
            "network",
            "devops",
            "terraform",
            "serverless",
            "digitalocean",
            "openstack",
        ),
        force=("cloud", "server", "database", "data", "internet", "network", "storage"),
    ),
    Domain(
        "networking",
        cues=("network", "router", "switch", "firewall", "tcp", "ip", "dns", "vpn", "lan", "wan"),
        sets=("network", "cisco", "networking"),
        force=("server", "router", "firewall", "network", "cloud", "internet"),
    ),
    Domain(
        "software",
        cues=(
            "software",
            "code",
            "programming",
            "app",
            "api",
            "git",
            "database",
            "frontend",
            "backend",
            "function",
            "algorithm",
            "compiler",
            "framework",
            "web",
            "developer",
        ),
        sets=("software", "dev", "code", "git", "programming", "web", "ui", "flowchart"),
        force=("database", "data", "server", "code", "api"),
    ),
    Domain(
        "weather",
        cues=(
            "weather",
            "rain",
            "storm",
            "climate",
            "snow",
            "wind",
            "forecast",
            "hurricane",
            "cloud",
            "clouds",
            "water cycle",
            "sky",
            "atmosphere",
        ),
        sets=("weather", "clouds"),
        force=(),  # weather KEEPS cartoon cloud/rain — never override to a tech icon
    ),
)

# Synonyms widen a plain noun toward the words icon titles actually use.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "server": ("server", "virtual machine", "vm", "compute", "ec2", "host", "instance"),
    "database": ("database", "db", "sql", "datastore", "cosmos", "rds"),
    "data": ("database", "storage", "data", "disk", "blob", "datastore"),
    "storage": ("storage", "disk", "blob", "bucket", "s3"),
    "internet": ("internet", "network", "globe", "web", "world", "wan"),
    "network": ("network", "vnet", "vpc", "subnet", "router"),
    "cloud": ("cloud", "cloud service", "cloud services"),
    "load balancer": ("load balancer", "balancer", "gateway"),
    "container": ("container", "kubernetes", "docker", "pod"),
    "queue": ("queue", "message", "bus", "topic"),
    "function": ("function", "lambda", "serverless"),
}


def _norm(s: str) -> str:
    return s.strip().lower().replace("_", " ").replace("-", " ")


# --------------------------------------------------------------------------- #
# Domain inference from the topic.
# --------------------------------------------------------------------------- #
def infer_domain(topic: str) -> str:
    """The best-matching domain for a topic, or "" (general/cartoon)."""
    t = f" {_norm(topic)} "
    best, best_score = "", 0
    for d in DOMAINS:
        score = sum(1 for cue in d.cues if f" {cue} " in t or t.strip() == cue)
        # a strong single signal (azure/aws/kubernetes in the title) is decisive
        score += sum(
            2
            for cue in ("azure", "aws", "gcp", "kubernetes", "docker")
            if cue in t and cue in d.cues
        )
        if score > best_score:
            best, best_score = d.id, score
    return best if best_score > 0 else ""


def _domain(domain_id: str) -> Domain | None:
    return next((d for d in DOMAINS if d.id == domain_id), None)


# --------------------------------------------------------------------------- #
# Semantic index over PUBLISHED imported icons (title tokens → candidate id).
# --------------------------------------------------------------------------- #
_INDEX: dict | None = None
_INDEX_TOKEN: int | None = None  # candidates_store.version() — auto-invalidates on any change


def _set_domain(set_name: str, library: str) -> str:
    blob = f"{_norm(set_name)} {_norm(library)}"
    for d in DOMAINS:
        if any(tok in blob for tok in d.sets):
            return d.id
    return ""


def _build_index() -> dict:
    """token -> list of {key, title, domain, ntoks} for every PUBLISHED candidate."""
    from engine import candidates_store

    idx = candidates_store.index()
    published = candidates_store.published_set()
    out: dict[str, list[dict]] = {}
    for key, it in idx.items():
        if key not in published or not it.get("strokes"):
            continue
        title = _norm(it.get("title", key))
        toks = [w for w in title.split() if len(w) > 1]
        dom = _set_domain(it.get("set_name", ""), it.get("library", ""))
        entry = {"key": key, "title": title, "domain": dom, "ntoks": len(toks)}
        # index by each title word AND the full title
        for tok in set(toks) | {title}:
            out.setdefault(tok, []).append(entry)
    return out


def _index() -> dict:
    global _INDEX, _INDEX_TOKEN
    from engine import candidates_store

    token = candidates_store.version()
    if _INDEX is None or token != _INDEX_TOKEN:
        _INDEX = _build_index()
        _INDEX_TOKEN = token
    return _INDEX


def refresh() -> None:
    global _INDEX, _INDEX_TOKEN
    _INDEX, _INDEX_TOKEN = None, None


def _lookup(term: str, domain_id: str) -> str | None:
    """Best published candidate id for a term within a domain, or None."""
    idx = _index()
    if not idx:
        return None
    terms = list(SYNONYMS.get(term, (term,)))
    best, best_score = None, 0.0
    for t in terms:
        for entry in idx.get(t, []):
            score = 0.0
            if entry["domain"] == domain_id and domain_id:
                score += 4
            elif entry["domain"]:
                score += 0.5  # an in-some-domain tech icon over nothing
            if entry["title"] == t:
                score += 3  # exact title match ("server" titled "Server")
            elif t in entry["title"].split():
                score += 1
            score += max(0.0, 1.5 - 0.25 * entry["ntoks"])  # prefer short, iconic titles
            if score > best_score:
                best, best_score = entry["key"], score
    return best if best_score >= 2 else None


def _has_cartoon(concept: str) -> bool:
    """True if the concept already composes to a real cartoon asset (recipe/family)."""
    from engine import icons

    try:
        return icons.compose(concept) is not None
    except Exception:
        return False


def resolve_concept(concept: str, domain_id: str = "") -> str:
    """Rewrite a plain concept to the best concrete asset id for the domain, or return it
    unchanged. Forced terms (cloud→tech in a cloud lesson) override the cartoon recipe;
    otherwise a concept that already has a cartoon asset is kept; only gap concepts
    (server/database/…) get mapped to a published imported icon."""
    if not concept:
        return concept
    norm = _norm(concept)
    dom = _domain(domain_id)
    if dom and norm in dom.force:
        hit = _lookup(norm, domain_id)
        if hit:
            return hit
    if _has_cartoon(norm):
        return concept  # tree/sun/cloud(weather) stay cartoon
    hit = _lookup(norm, domain_id)
    return hit or concept


def vocabulary(domain_id: str = "", limit: int = 40) -> list[str]:
    """Clean, readable drawable names to PREFER in the Story prompt for a domain. Filters
    cryptic abbreviations (2-letter titles) and overlong names; prefers short, few-word,
    real terms the model will actually reach for."""
    idx = _index()
    seen: dict[str, int] = {}
    for entries in idx.values():
        for e in entries:
            if domain_id and e["domain"] != domain_id:
                continue
            t = e["title"]
            if len(t) < 4 or len(t) > 26 or t in seen:
                continue
            seen[t] = e["ntoks"]
    names = sorted(seen, key=lambda t: (seen[t], len(t)))  # few-word, short, real names first
    return names[:limit]
