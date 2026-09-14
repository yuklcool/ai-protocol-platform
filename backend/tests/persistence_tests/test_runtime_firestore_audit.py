from pathlib import Path


def test_business_runtime_has_no_direct_firestore_imports() -> None:
    """Business/runtime code must depend on db.persistence, not Firestore directly.

    Firestore remains a supported repository backend; this guard only prevents
    higher layers from bypassing the provider-neutral persistence facade.
    """
    backend_root = Path(__file__).resolve().parents[2]
    roots = [
        backend_root / "admin",
        backend_root / "adk",
        backend_root / "channels",
        backend_root / "buckets",
        backend_root / "rag",
        backend_root / "skills",
        backend_root / "protocols",
        backend_root / "tools" / "documents",
    ]
    forbidden = (
        "from db.firestore import",
        "import db.firestore",
        "google.cloud.firestore",
    )

    offenders: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if any(marker in text for marker in forbidden):
                offenders.append(str(path.relative_to(backend_root.parent)))

    assert offenders == [], (
        "Business/runtime modules must use db.persistence; direct Firestore "
        f"imports found in: {', '.join(sorted(offenders))}"
    )
