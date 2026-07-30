"""Spec-scenario tests for reconstruct-project-foundation. 12 scenarios, parametrized."""
from __future__ import annotations
import re
import subprocess
from pathlib import Path
import pytest

R = Path(__file__).resolve().parents[5]
N = {"OrderCreated", "InventoryReserved", "PaymentAuthorized", "OrderNotificationSent"}
N_TARGET = {"InventoryRejected", "OrderConfirmed", "OrderCancelled"}
D = {k: R / v for k, v in {
    "R": "README.md", "P": "PRD.md", "A": "ARCHITECTURE.md",
    "D": "DESIGN.md", "G": "docs/GLOSSARY.md", "I": "docs/adr/README.md",
}.items()}
X = ["backend/app/**", "backend/README.md", "backend/pyproject.toml",
     "backend/.env*", "backend/Dockerfile", "backend/docker-compose.yml",
     "backend/alembic/**", "backend/conftest.py", "backend/**/tests/**",
     "backend/**/test_*.py", "backend/**/conftest.py", ".github/**",
     "frontend/**", "openspec/config.yaml", "skills-lock.json"]


def read(p): return Path(p).read_text()
def links_of(t): return {u.split("#")[0] for _, u in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", t) if u and not u.startswith(("http", "mailto"))}
def g(*a): return subprocess.run(["git", *a], cwd=R, capture_output=True, text=True, check=True).stdout
def v(p, b): return (b.parent / p).resolve()

# S12 R9 — baseline + excluded paths clean
def test_s12_baseline_captured():
    b = Path(g("rev-parse", "--git-common-dir").strip()) / "gentle-ai/sdd-baselines/reconstruct-project-foundation/f3170af-clean"
    assert b.exists() and (b / "MANIFEST.md").exists() and (b / "paths.sha256").exists()
def test_s12_excluded_paths_clean():
    # Doc-work range (W1..W7) MUST NOT have touched any excluded path.
    assert not g("diff", "--stat", "f3170af", "82694d9", "--", *X).strip()
    # Working tree: this remediation batch was explicitly authorized to add PyYAML to the
    # dev dependency group of backend/pyproject.toml. Allow ONLY that permitted change.
    other_x = [p for p in X if p != "backend/pyproject.toml"]
    assert not g("diff", "--stat", "HEAD", "--", *other_x).strip()
    assert not subprocess.run(["git", "status", "--porcelain", *other_x], cwd=R, capture_output=True, text=True).stdout.strip()
    head_pp = g("diff", "HEAD", "--", "backend/pyproject.toml")
    assert "PyYAML" in head_pp and head_pp.count("\n+") <= 2

# S1 R1 — README
@pytest.mark.parametrize("needle", ["five-minute", "layout", "documentation index", "contributing"])
def test_s1_readme_sections(needle):
    assert needle in read(D["R"]).lower()
def test_s1_readme_links_resolve():
    links = links_of(read(D["R"]))
    assert len(links) >= 5 and all((D["R"].parent / x).resolve().exists() for x in links)
@pytest.mark.parametrize("tgt", ["prd.md", "architecture.md", "design.md", "docs/glossary.md", "docs/adr/"])
def test_s1_readme_links_each_root(tgt):
    assert tgt in read(D["R"]).lower()

# S2 R2 — ownership
def test_s2_no_personas_in_arch():
    assert not re.search(r"^##+\s+.*persona", read(D["A"]), re.M | re.I)
def test_s2_no_topology_in_prd():
    assert not re.search(r"^##+\s+.*topology", read(D["P"]), re.M | re.I)

# S3 R3 — matrix honesty
@pytest.mark.parametrize("status", ["implemented", "partial", "target"])
def test_s3_matrix_status_enum(status):
    assert f"| {status} |" in read(D["A"])
def test_s3_no_dishonest_live_claim():
    t = read(D["A"])
    assert "AMQP consumer is live" not in t and "outbox worker is running" not in t
def test_s3_prd_honest_amqp():
    assert not re.search(r"(?i)(amqp|rabbitmq|consumer|outbox)\s+is\s+(live|implemented|running)", read(D["P"]))

# S4 R4 — event vocabulary
def test_s4_glossary_events_present():
    t = read(D["G"])
    for e in (N | N_TARGET):
        assert e in t
def test_s4_glossary_matches_published_events():
    found = set()
    for p in (R / "backend/app/modules").glob("*/domain/events/*.py"):
        found |= {m.group(1) for m in re.finditer(r"@dataclass\s*\nclass\s+(\w+)", read(p), re.M)}
    assert found == N
def test_s4_state_machine_transitions():
    x = read(R / "backend/app/modules/orders/domain/services/order_domain_service.py")
    for pat in ('"pending": {"inventory_reserved", "cancelled"}',
                '"inventory_reserved": {"payment_authorized", "cancelled"}',
                '"payment_authorized": {"confirmed", "cancelled"}'):
        assert pat in x

# S5 R4 — no invented capability
@pytest.mark.parametrize("m", ["orders", "inventory", "payments", "notifications"])
def test_s5_router_health_only(m):
    verbs = {x.group(1) for x in re.finditer(r"@router\.(\w+)\([\"']([^\"']+)[\"']", read(R / f"backend/app/modules/{m}/api/routes/v1/router.py"))}
    assert verbs == {"get"}
def test_s5_no_shared_infra():
    dirs = {p.name for p in (R / "backend/app/shared").iterdir() if p.is_dir() and p.name != "__pycache__"}
    assert dirs <= {"config", "db"}

# S6 R5 — PRD product contract
@pytest.mark.parametrize("needle", ["portfolio", "iam", "catalog", "cart", "checkout",
                                    "orders", "inventory", "payments", "notifications",
                                    "outbox", "choreography", "idempotent", "deterministic"])
def test_s6_prd_declares(needle):
    assert needle in read(D["P"]).lower()

# S7 R6 — overlap is linked, not copied
def test_s7_arch_links_glossary():
    assert "docs/glossary.md" in read(D["A"]).lower()
def test_s7_arch_links_adr_index():
    assert "docs/adr/readme.md" in read(D["A"]).lower()

# S8 R6 — glossary + ADR content
def test_s8_glossary_producer_consumer():
    assert "producer" in read(D["G"]).lower() and "consumer" in read(D["G"]).lower()
@pytest.mark.parametrize("n", range(1, 6))
@pytest.mark.parametrize("section", ["## status", "## context", "## decision", "## consequences", "## options considered"])
def test_s8_adrs_have_required_sections(n, section):
    path = next((R / "docs/adr").glob(f"{n:04d}-*.md"))
    assert section in path.read_text().lower()
@pytest.mark.parametrize("n", range(1, 6))
def test_s8_adr_index_matches(n):
    assert f"{n:04d}" in read(D["I"])

# S9 R7 / S10 R8 — cross-link resolve (anti-ghost: every doc must contribute >0)
def test_s9_s10_all_links_resolve():
    bad, per_doc = [], {}
    for k, doc in D.items():
        links = links_of(read(doc))
        per_doc[k] = len(links)
        for x in links:
            if not v(x, doc).exists():
                bad.append(f"{doc.name} -> {x}")
    for k, n in per_doc.items():
        assert n > 0
    assert not bad

# S11 R8 — 400-line budget
@pytest.mark.parametrize("k", list(D.keys()))
def test_s11_each_root_doc_under_400_lines(k):
    assert sum(1 for _ in D[k].open()) <= 400

# DESIGN-specific
def test_design_target_notice():
    assert "target design notice" in read(D["D"]).lower()
def test_design_yaml_alpha():
    import yaml
    m = re.search(r"^---\n(.*?)\n---", read(D["D"]), re.S)
    assert m and yaml.safe_load(m.group(1))["version"] == "alpha"

# OpenSpec contract consistency (W7.6)
def test_openspec_artifacts_present():
    p = R / "openspec/changes/archive/2026-07-28-reconstruct-project-foundation"
    for f in ("proposal.md", "design.md", "tasks.md", "specs/project-foundation-docs/spec.md"):
        assert (p / f).exists()
def test_proposal_declares_published_now():
    assert "Published Git Now wins" in read(R / "openspec/changes/archive/2026-07-28-reconstruct-project-foundation/proposal.md")

# Backend dep guard
def test_pydantic_settings_declared():
    assert "pydantic-settings" in read(R / "backend/pyproject.toml")
