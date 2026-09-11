from pathlib import Path


def rep(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {n}")
    return text.replace(old, new, 1)

p = Path('backend/v11_server.py')
s = p.read_text()

old_deadline = '''def _deadline_ok(deadline_str: str) -> bool:
    try:
        d = date.fromisoformat(deadline_str)
        return d >= date.today()
    except Exception:
        return True  # if missing, don’t block


def _is_expired(deadline_str: str) -> bool:
    try:
        d = date.fromisoformat(deadline_str)
        return d < date.today()
    except Exception:
        return False
'''
new_deadline = r'''def _deadline_dates(deadline_str: str) -> List[date]:
    """Extract plausible application dates from ISO or prose deadline fields."""
    raw = str(deadline_str or "").strip()
    if not raw:
        return []
    found: List[date] = []

    # ISO dates anywhere in the field.
    for year, month, day in re.findall(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", raw):
        try:
            found.append(date(int(year), int(month), int(day)))
        except ValueError:
            pass

    # Numeric US dates such as 04/01/2019.
    for month, day, year in re.findall(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b", raw):
        try:
            found.append(date(int(year), int(month), int(day)))
        except ValueError:
            pass

    # Month-name dates such as April 1, 2019.
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10,
        "nov": 11, "dec": 12,
    }
    for month_name, day, year in re.findall(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+(\d{1,2}),?\s+(20\d{2})\b",
        raw,
        flags=re.I,
    ):
        try:
            found.append(date(int(year), months[month_name.lower()], int(day)))
        except ValueError:
            pass

    return sorted(set(found))


def _deadline_ok(deadline_str: str) -> bool:
    raw = str(deadline_str or "").strip()
    if not raw:
        return True
    dates = _deadline_dates(raw)
    if dates:
        return max(dates) >= date.today()
    # Explicit rolling/year-round language is not treated as expired when no fixed date exists.
    lowered = raw.lower()
    if any(term in lowered for term in ("year-round", "year round", "rolling", "continuous")):
        return True
    # Unknown prose deadlines are allowed through this layer but remain subject to official-notice review.
    return True


def _is_expired(deadline_str: str) -> bool:
    raw = str(deadline_str or "").strip()
    if not raw:
        return False
    dates = _deadline_dates(raw)
    if dates:
        return max(dates) < date.today()
    return False


def _is_actionable_opportunity(gr: Dict[str, Any]) -> Tuple[bool, str]:
    """Reject informational/forecast notices that are not currently accepting applications."""
    title = str(gr.get("title") or "")
    summary = str(gr.get("summary") or "")
    blob = f"{title} {summary}".lower()

    non_actionable_phrases = (
        "notice of intent to issue",
        "notice of intent (noi)",
        "this notice of intent",
        "informational purposes only",
        "not requesting applications at this time",
        "not requesting comments or applications",
        "may issue a notice of funding opportunity",
        "forecasted opportunity",
        "forecast only",
        "pre-solicitation notice",
        "presolicitation notice",
    )
    if any(phrase in blob for phrase in non_actionable_phrases):
        return False, "This record is informational or forecast-only and is not a current application opportunity."

    # Titles beginning with NOI are treated conservatively when the body also describes a future NOFO.
    if re.search(r"\bNOI\b", title, flags=re.I) and any(term in blob for term in ("may issue", "intends to issue", "will issue")):
        return False, "This is a notice of intent rather than an open application opportunity."
    return True, ""
'''
s = rep(s, old_deadline, new_deadline, 'deadline/actionable helpers')

old_loop = '''        for gr in grants:
            # GrantForgeUSA does not sell student-aid or student-applicant services.
            if _student_applicant_opportunity(gr):
                continue

            # hide expired unless explicitly requested
            close_date = gr.get("close_date") or gr.get("deadline") or ""
            is_expired = _is_expired(close_date)
            if not include_expired and is_expired:
                continue
'''
new_loop = '''        for gr in grants:
            # GrantForgeUSA does not sell student-aid or student-applicant services.
            if _student_applicant_opportunity(gr):
                continue

            actionable, _ = _is_actionable_opportunity(gr)
            if not actionable:
                continue

            # Hide expired opportunities, including prose deadline fields whose latest
            # application date is already in the past.
            close_date = gr.get("close_date") or gr.get("deadline") or ""
            is_expired = _is_expired(close_date)
            if not include_expired and is_expired:
                continue
'''
s = rep(s, old_loop, new_loop, 'shortlist actionable/deadline gate')
p.write_text(s)

p = Path('backend/tests/test_v11_server.py')
t = p.read_text()
extra = r'''


def test_notice_of_intent_is_not_actionable_even_when_terms_match():
    grant = {
        "title": "DE-FOA-0003646 Notice of Intent to Issue DE-FOA-0003647 Accelerating Scale-up and Pre-piloting of Emerging Chemical Technologies (ASPECT)",
        "summary": "This Notice of Intent is for informational purposes only. DOE is not requesting comments or applications at this time and may issue a Notice of Funding Opportunity.",
    }
    ok, note = srv._is_actionable_opportunity(grant)
    assert ok is False
    assert "not a current application opportunity" in note


def test_old_prose_deadline_is_recognized_as_expired():
    deadline = "Applications are accepted year-round. Complete applications must be received no later than October 31, 2018, or April 1, 2019."
    assert srv._deadline_dates(deadline)[-1].isoformat() == "2019-04-01"
    assert srv._is_expired(deadline) is True
    assert srv._deadline_ok(deadline) is False


def test_future_prose_deadline_is_not_expired():
    deadline = "Applications must be received by December 31, 2026."
    assert srv._is_expired(deadline) is False
    assert srv._deadline_ok(deadline) is True


def test_shortlist_filters_informational_noi_before_scoring(monkeypatch):
    payload = _payload("Example Small Business", "energy, manufacturing, efficiency", "Small Business")
    payload["state"] = "Minnesota"
    payload["amountRequested"] = 90000
    noi = {
        "title": "Notice of Intent to Issue Future Energy NOFO",
        "summary": "This Notice of Intent is for informational purposes only; applications are not being requested at this time.",
        "eligibility_codes": ["23"],
        "deadline": "2026-12-31",
        "min_amount": 1000,
        "max_amount": 500000,
        "tags": ["energy", "manufacturing", "efficiency"],
        "sector": "energy / manufacturing efficiency",
    }
    rows, _ = srv.shortlist(payload, pinned_grant=noi)
    assert rows == []
'''
if 'test_notice_of_intent_is_not_actionable_even_when_terms_match' not in t:
    t += extra
p.write_text(t)
print('actionable/deadline guardrails patched')
