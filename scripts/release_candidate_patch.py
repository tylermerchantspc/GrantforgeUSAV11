from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {count}")
    return text.replace(old, new, 1)


# Frontend
app_path = Path("frontend/grantforge-frontend/src/App.jsx")
app = app_path.read_text()
app = replace_once(
    app,
    '''const PRICE_RANGE = "$9.99–$199.99";

function serviceFeeFor(category, annualBudget) {
  if (String(category || "").toLowerCase() === "teacher (classroom)") return "$9.99";
  const budget = Number(annualBudget);
  if (!Number.isFinite(budget) || budget <= 0) return "Select your organization details";
  if (budget <= 500000) return "$49.99";
  if (budget <= 2000000) return "$99.99";
  return "$199.99";
}
''',
    '''const FLAT_DRAFT_PRICE = "$49.99";

function serviceFeeFor() {
  return FLAT_DRAFT_PRICE;
}
''',
    "frontend price function",
)
app = replace_once(app, '  const serviceFee = serviceFeeFor(form.category, form.annualBudget);', '  const serviceFee = serviceFeeFor();', "frontend service fee call")
app = replace_once(app, 'Free grant matching and preview · Pay only when you select a full draft', 'Free grant matching and preview · One full proposal draft: $49.99', "service banner")
app = app.replace(
    'Payment card information is collected and processed by the payment provider used at checkout. GrantForgeUSA does not ask you to place card numbers, bank credentials, passwords, Social Security numbers, protected health information, or student education records in the project intake.',
    'Payment card information is collected and processed by the payment provider used at checkout. GrantForgeUSA does not ask you to place card numbers, bank credentials, passwords, Social Security numbers, or protected health information in the project intake.',
)
app = replace_once(
    app,
    'Payment purchases the selected drafting service and authorizes GrantForgeUSA to generate the full draft using the submitted intake. All sales are final and non-refundable except where a refund is required by applicable law. Correct your information and selected opportunity before submitting payment.',
    'Payment purchases an immediately performed customized digital drafting service for the selected opportunity and authorizes GrantForgeUSA to begin generation using the submitted intake. Because the work is prepared specifically for the customer, all sales are final and non-refundable once generation begins except where required by applicable law or when GrantForgeUSA fails to deliver the purchased service. Funding denial, agency changes, customer ineligibility, or inaccurate customer-supplied information do not create a refund entitlement. GrantForgeUSA may correct or re-perform a technically defective delivery when appropriate.',
    "terms refund language",
)
app = replace_once(
    app,
    'Tell GrantForgeUSA about your organization and project. Our proprietary software screens federal opportunities, ranks the strongest matches, shows a preliminary qualification level, and gives you a proposal preview before you decide to purchase the full draft.',
    'Tell GrantForgeUSA about the eligible applicant and project. Our proprietary software screens federal opportunities, ranks the strongest matches, shows a preliminary qualification level, and gives you a proposal preview before you decide to purchase the full draft.',
    "hero scope",
)
app = replace_once(
    app,
    '''              <span>Selected full proposal draft</span>
              <strong>{PRICE_RANGE}</strong>
              <p>Teacher: $9.99 · Organizations ≤$500k: $49.99 · $500k–$2M: $99.99 · Over $2M: $199.99. All sales final except where required by law.</p>''',
    '''              <span>One selected full proposal draft</span>
              <strong>{FLAT_DRAFT_PRICE}</strong>
              <p>One flat price for every supported applicant type and funding amount. Search, matching, official opportunity links, and the quick preview remain free. Customized drafting begins immediately after payment; final-sale terms apply.</p>''',
    "pricing card",
)
app = replace_once(app, '                  Organization name <em>*</em>', '                  Applicant / organization name <em>*</em>', "applicant label")
app = replace_once(
    app,
    '''                    <option value="">Select type</option>
                    <option>Teacher (Classroom)</option>
                    <option>School / District</option>
                    <option>Church / Faith Org</option>
                    <option>501c3 Nonprofit</option>
                    <option>Small Business</option>
                    <option>City / Municipality</option>
                    <option>Other</option>
                  </select>
                  {form.category === "Teacher (Classroom)" && (
                    <small className="field-guidance">Many federal opportunities require the school or district - not an individual teacher - to be the eligible applicant. Enter the school or district information where applicable.</small>
                  )}''',
    '''                    <option value="">Select type</option>
                    <option>K-12 School / District / Educator</option>
                    <option>College / University / Research Institution</option>
                    <option>Church / Faith Organization</option>
                    <option>501(c)(3) Nonprofit</option>
                    <option>Nonprofit / Community Organization</option>
                    <option>Small Business</option>
                    <option>For-Profit Organization</option>
                    <option>City / County / Local Government</option>
                    <option>State Government / Agency</option>
                    <option>Tribal Government / Organization</option>
                    <option>Public Housing Authority</option>
                    <option>Individual / Independent Applicant</option>
                    <option>Other Eligible Applicant</option>
                  </select>
                  {form.category === "K-12 School / District / Educator" && (
                    <small className="field-guidance">Use the school or district that would be the legal applicant. A teacher or educator may be the contact when authorized by the applicant organization.</small>
                  )}
                  {form.category === "College / University / Research Institution" && (
                    <small className="field-guidance">Use the institution as the applicant and the professor, principal investigator, dean, or grant administrator as the contact.</small>
                  )}''',
    "applicant categories",
)
app = replace_once(
    app,
    '                            I have checked my information and selected grant. I agree to the <a href="/terms" target="_blank">Terms</a> and understand all sales are final and non-refundable except where required by law.',
    '                            I have checked my information and selected grant. I agree to the <a href="/terms" target="_blank">Terms</a>, authorize GrantForgeUSA to begin the customized drafting service immediately after payment, and understand the $49.99 service is final and non-refundable once generation begins except where required by law or if GrantForgeUSA fails to deliver the purchased service. Funding is not guaranteed.',
    "checkout final sale acknowledgement",
)
app = app.replace('Payment starts the full draft for the opportunity selected above.', 'Payment starts the customized full-draft service immediately for the opportunity selected above.')
app_path.write_text(app)

# Grants.gov adapter
live_path = Path("backend/grantsgov_live.py")
live = live_path.read_text()
live = replace_once(
    live,
    '''APPLICANT_ELIGIBILITY_CODES = {
    "EDU": ["05", "99"],
    "NONPROFIT": ["12", "13", "99"],
    "SMALL_BUSINESS": ["23", "99"],
    "GOV_LOCAL": ["01", "02", "04", "99"],
}''',
    '''APPLICANT_ELIGIBILITY_CODES = {
    "EDU_K12": ["05", "99"],
    "HIGHER_ED": ["06", "20", "99"],
    "NONPROFIT_501C3": ["12", "99"],
    "NONPROFIT": ["12", "13", "99"],
    "SMALL_BUSINESS": ["23", "99"],
    "FOR_PROFIT": ["22", "99"],
    "GOV_LOCAL": ["01", "02", "04", "99"],
    "GOV_STATE": ["00", "99"],
    "TRIBAL": ["07", "11", "99"],
    "HOUSING": ["08", "99"],
    "INDIVIDUAL": ["21", "99"],
    "OTHER": ["25", "99"],
}''',
    "Grants.gov applicant codes",
)
live = replace_once(
    live,
    '''    if any(
        term in joined
        for term in (
            "school district",
            "independent school",
            "public institution of higher education",
            "private institution of higher education",
            "education agencies",
        )
    ):
        tags.extend(["school", "district", "education"])''',
    '''    if any(term in joined for term in ("school district", "independent school", "education agencies")):
        tags.extend(["school", "district", "education", "k12"])
    if any(term in joined for term in ("public institution of higher education", "private institution of higher education", "institution of higher education")):
        tags.extend(["higher education", "college", "university", "research institution", "education"])''',
    "education eligibility tags",
)
live_path.write_text(live)

# Backend
server_path = Path("backend/v11_server.py")
server = server_path.read_text()
server = replace_once(
    server,
    '''# Public per-draft pricing
TEACHER_PRICE = 9.99
SMALL_ORG_PRICE = 49.99
MEDIUM_ORG_PRICE = 99.99
LARGE_ORG_PRICE = 199.99''',
    '''# Public per-draft pricing: one flat fee regardless of applicant type or grant size.
FLAT_DRAFT_PRICE = float(os.getenv("GRANT_DRAFT_PRICE", "49.99"))''',
    "backend price constants",
)
server = replace_once(
    server,
    '''INTAKE_TYPE_MAP = {
    "teacher (classroom)": "EDU",
    "school / district": "EDU",
    "church / faith org": "NONPROFIT",
    "501c3 nonprofit": "NONPROFIT",
    "small business": "SMALL_BUSINESS",
    "city / municipality": "GOV_LOCAL",
    "other": "NONPROFIT",
}''',
    '''INTAKE_TYPE_MAP = {
    "k-12 school / district / educator": "EDU_K12",
    "college / university / research institution": "HIGHER_ED",
    "church / faith organization": "NONPROFIT",
    "501(c)(3) nonprofit": "NONPROFIT_501C3",
    "nonprofit / community organization": "NONPROFIT",
    "small business": "SMALL_BUSINESS",
    "for-profit organization": "FOR_PROFIT",
    "city / county / local government": "GOV_LOCAL",
    "state government / agency": "GOV_STATE",
    "tribal government / organization": "TRIBAL",
    "public housing authority": "HOUSING",
    "individual / independent applicant": "INDIVIDUAL",
    "other eligible applicant": "OTHER",
    "teacher (classroom)": "EDU_K12",
    "school / district": "EDU_K12",
    "church / faith org": "NONPROFIT",
    "501c3 nonprofit": "NONPROFIT_501C3",
    "city / municipality": "GOV_LOCAL",
    "other": "OTHER",
}''',
    "intake type map",
)
server = replace_once(server, '    return INTAKE_TYPE_MAP.get(c, "NONPROFIT")', '    return INTAKE_TYPE_MAP.get(c, "OTHER")', "default applicant type")
server = replace_once(
    server,
    '''def price_for(category: str, annual_budget: float) -> float:
    category_key = (category or "").strip().lower()
    if category_key == "teacher (classroom)":
        return TEACHER_PRICE
    if annual_budget <= 500_000:
        return SMALL_ORG_PRICE
    if annual_budget <= 2_000_000:
        return MEDIUM_ORG_PRICE
    return LARGE_ORG_PRICE''',
    '''def price_for(category: str, annual_budget: float) -> float:
    """Return the single public price for one customized full proposal draft."""
    _ = category, annual_budget
    return FLAT_DRAFT_PRICE''',
    "backend price function",
)

start = server.index("def _is_eligible_for_applicant(")
end = server.index("\n\ndef shortlist(", start)
eligible_fn = '''def _is_eligible_for_applicant(gr: Dict[str, Any], applicant_type: str) -> bool:
    """Use official Grants.gov applicant codes first; fall back to normalized text for fixtures/legacy data."""
    code_map = {
        "EDU_K12": {"05", "99"},
        "HIGHER_ED": {"06", "20", "99"},
        "NONPROFIT_501C3": {"12", "99"},
        "NONPROFIT": {"12", "13", "99"},
        "SMALL_BUSINESS": {"23", "99"},
        "FOR_PROFIT": {"22", "99"},
        "GOV_LOCAL": {"01", "02", "04", "99"},
        "GOV_STATE": {"00", "99"},
        "TRIBAL": {"07", "11", "99"},
        "HOUSING": {"08", "99"},
        "INDIVIDUAL": {"21", "99"},
        "OTHER": {"25", "99"},
    }
    codes = {str(code or "").strip().zfill(2) for code in (gr.get("eligibility_codes") or []) if str(code or "").strip()}
    if codes:
        return bool(codes & code_map.get(applicant_type, {"99"}))
    title = (gr.get("title") or "").lower()
    tags = " ".join(normalized_tags(gr.get("tags", [])))
    elig = " ".join(str(e).lower() for e in gr.get("eligible_types", []))
    haystack = f"{title} {tags} {elig}"
    if "unrestricted" in haystack:
        return True
    if "sbir" in haystack or "sttr" in haystack:
        return applicant_type == "SMALL_BUSINESS"
    if "cdbg" in haystack:
        return applicant_type == "GOV_LOCAL"
    needles = {
        "EDU_K12": ("school district", "school", "teacher", "educator", "k12", "classroom"),
        "HIGHER_ED": ("higher education", "college", "university", "research institution"),
        "NONPROFIT_501C3": ("501", "501(c)(3)", "nonprofit"),
        "NONPROFIT": ("nonprofit", "community-based", "community organization", "faith-based"),
        "SMALL_BUSINESS": ("small business", "startup", "microenterprise"),
        "FOR_PROFIT": ("for-profit", "for profit", "commercial organization"),
        "GOV_LOCAL": ("municipality", "city", "township", "county", "local government", "special district"),
        "GOV_STATE": ("state government", "state agency"),
        "TRIBAL": ("tribal government", "tribal organization", "native american"),
        "HOUSING": ("public housing", "housing authority", "indian housing"),
        "INDIVIDUAL": ("individual", "individual applicant"),
        "OTHER": ("other",),
    }
    return any(term in haystack for term in needles.get(applicant_type, ()))'''
server = server[:start] + eligible_fn + server[end:]
server = server.replace('    required = 2 if applicant_type in ("EDU", "SMALL_BUSINESS") else 1', '    required = 2 if applicant_type in ("EDU_K12", "HIGHER_ED", "SMALL_BUSINESS", "FOR_PROFIT") else 1')

n_start = server.index("def build_narrative(")
n_end = server.index("\n\ndef build_draft_text(", n_start)
narrative_fn = '''def build_narrative(intake: Dict[str, Any], grant: Dict[str, Any]) -> str:
    """Build an applicant-aware proposal draft without inventing facts, metrics, or compliance claims."""
    intake = dict(intake or {})
    org = _organization_name(intake)
    project = (intake.get("projectTitle") or "Proposed Project").strip()
    category = (intake.get("category") or intake.get("who") or "eligible applicant").strip()
    applicant_type = normalize_applicant_type(category)
    audience = (intake.get("audience") or "the intended beneficiaries").strip().rstrip(".")
    timeline = (intake.get("timeline") or "the proposed grant period").strip().rstrip(".")
    need = (intake.get("need") or "").strip()
    notes = (intake.get("notes") or "").strip()
    amount = _safe_float(intake.get("amountRequested"))
    annual_budget = _safe_float(intake.get("annualBudget"), 0)
    kws = normalized_keywords((intake.get("keywords") or "").strip())
    sector = infer_client_sector(kws) or "the proposed project area"
    g_title = _sanitize_text(grant.get("title") or "Federal funding opportunity", 240)
    g_program = _sanitize_text(grant.get("program") or grant.get("agency") or "Federal program", 240)
    g_deadline = _sanitize_text(grant.get("deadline") or "TBA", 80)
    g_min = _safe_float(grant.get("min_amount"), 0)
    g_max = _safe_float(grant.get("max_amount"), 0)
    g_summary = _sanitize_text(grant.get("summary") or "", 900)
    g_match = int(_safe_float(grant.get("requires_match_percent"), 0))
    req_str = f"${amount:,.0f}" if amount > 0 else "the amount shown in the final budget"
    budget_str = f"${annual_budget:,.0f}" if annual_budget > 0 else "not supplied"
    focus = ", ".join(kws[:5]) if kws else project
    need_text = need or notes or f"The applicant identified a need directly related to {focus}."
    profile = {
        "EDU_K12": ("education applicant", "instructional or school-system delivery", "learners, educators, and the school community"),
        "HIGHER_ED": ("higher-education or research institution", "research, teaching, institutional, or sponsored-program delivery", "the identified research, education, or community beneficiaries"),
        "NONPROFIT_501C3": ("501(c)(3) nonprofit", "mission-driven program delivery", "the identified beneficiaries and community partners"),
        "NONPROFIT": ("nonprofit or community organization", "mission-driven program delivery", "the identified beneficiaries and community partners"),
        "SMALL_BUSINESS": ("small business", "business, innovation, operational, or commercialization activity", "the business, workforce, customers, and other stated beneficiaries"),
        "FOR_PROFIT": ("for-profit organization", "business, innovation, operational, or commercialization activity", "the organization and other stated beneficiaries"),
        "GOV_LOCAL": ("local-government applicant", "public-service, infrastructure, or community implementation", "residents and other stated public beneficiaries"),
        "GOV_STATE": ("state-government applicant", "statewide or agency-led implementation", "the stated public beneficiaries"),
        "TRIBAL": ("Tribal applicant", "Tribal government or organization-led implementation", "the stated Tribal community beneficiaries"),
        "HOUSING": ("public-housing applicant", "housing, resident-service, or community implementation", "residents and other stated beneficiaries"),
        "INDIVIDUAL": ("individual applicant", "applicant-led project implementation", "the stated beneficiaries"),
        "OTHER": ("eligible applicant", "project implementation", "the stated beneficiaries"),
    }.get(applicant_type, ("eligible applicant", "project implementation", "the stated beneficiaries"))
    entity_label, delivery_frame, beneficiary_frame = profile
    opportunity_range = []
    if g_min > 0:
        opportunity_range.append(f"published floor ${g_min:,.0f}")
    if g_max > 0:
        opportunity_range.append(f"published ceiling ${g_max:,.0f}")
    range_text = ", ".join(opportunity_range) if opportunity_range else "award range not captured in the current synopsis"
    match_text = f" A {g_match}% match is listed and must be verified against the official notice." if g_match > 0 else ""
    synopsis_text = f" The current Grants.gov synopsis states: {g_summary}" if g_summary else ""
    activity_language = {
        "energy / manufacturing efficiency": "procurement or installation planning, operational implementation, performance measurement, and documented efficiency results",
        "telehealth / healthcare": "service design, implementation protocols, access measures, quality monitoring, and documented health-service outcomes",
        "workforce development": "participant recruitment, training or credential activities, employer/partner coordination, and employment or skill outcomes",
        "education / STEM": "instructional or research design, educator/participant engagement, implementation fidelity, and learning or research outcomes",
        "housing / community development": "project delivery, resident/community engagement, implementation milestones, and measurable community outcomes",
        "public safety / emergency management": "readiness activities, implementation milestones, interagency coordination, and measurable safety or resilience outcomes",
        "conservation / environment": "field or implementation activities, stewardship milestones, monitoring, and measurable environmental outcomes",
        "arts / culture": "creative or cultural activities, public engagement, implementation milestones, and measurable participation or access outcomes",
        "entrepreneurship / innovation": "research or development activity, validation milestones, technical progress, and commercialization or adoption measures",
    }.get(sector, "defined project activities, documented milestones, responsible implementation, and measurable outcomes")
    sections = [
        "Executive Summary\n" + f"{org}, a {entity_label}, seeks {req_str} through {g_title} to carry out '{project}' over {timeline}. The project is intended to serve {audience}. Based on the information supplied by the applicant, the proposed work centers on {focus} and falls within {sector}. This draft frames the project around the selected federal opportunity while preserving applicant responsibility for every factual statement, target, attachment, certification, and final submission decision.",
        "Funding Opportunity Alignment\n" + f"Selected opportunity: {g_title}. Program/agency reference: {g_program}. Current deadline captured by GrantForgeUSA: {g_deadline}. Funding information captured from the opportunity: {range_text}. The requested amount is {req_str}.{match_text}{synopsis_text} Before submission, the applicant must compare this draft with the complete current notice, amendments, eligibility rules, required registrations, and application package.",
        "Statement of Need\n" + f"The applicant described the underlying need as follows: {need_text} The proposal should support this statement with applicant-verified local data, baseline information, documented demand, prior results, citations, or other evidence required by the funding notice. GrantForgeUSA does not invent those facts when they are not supplied in the intake.",
        "Program Description\n" + f"'{project}' will use {delivery_frame} focused on {activity_language}. The working scope is designed around {audience} and the applicant's stated priorities: {focus}. Final activities, quantities, locations, staffing assignments, partners, procurement specifications, and methods should be confirmed by {org} before submission and revised wherever the official notice requires a different structure.",
        "Goals, Objectives, and Performance Measures\n" + f"The draft goal is to address the stated need through a focused {sector} project with measurable implementation and outcome evidence. Before submission, {org} should set applicant-owned targets for: (1) the quantity and timing of major activities or deliverables; (2) the primary outcome expected for {audience}; and (3) completion of required project, reporting, and compliance milestones. Baselines and numerical targets should come from the applicant's records, research plan, operating data, or other defensible evidence rather than default percentages.",
        "Implementation Plan\n" + f"The proposed period is {timeline}. A final work plan should identify the responsible lead for each major task, milestone dates, partner or vendor responsibilities, dependencies, and the evidence used to document completion. The implementation sequence should cover startup/readiness, core delivery, monitoring and adjustment, and closeout/reporting. Where the notice uses required phases or milestones, those requirements supersede this general structure.",
        "Target Population / Beneficiaries\n" + f"The intake identifies {audience} as the primary audience or beneficiary group. For this {entity_label}, the proposal should explain how that audience connects to {beneficiary_frame}, why the project design is appropriate for them, and how participation, access, research subjects, customers, residents, or other beneficiaries will be defined where applicable. Any demographic, geographic, or participation claims must be verified by the applicant.",
        "Organizational Capacity\n" + f"The applicant reported an annual operating or organizational budget of approximately {budget_str}. The final application should describe only verified capacity: authorized leadership, relevant personnel or investigators, prior experience, required registrations, financial systems, facilities, partnerships, and other qualifications specifically requested by the notice. This draft does not assume that {org} possesses a certification, internal control, prior award history, staffing level, or partnership unless the applicant supplied and confirms that fact.",
        "Budget Use\n" + f"The working request is {req_str}. The final budget narrative should connect each cost directly to a confirmed project activity and use the cost categories, allowability rules, indirect-cost treatment, match requirements, and documentation standards in the official notice. GrantForgeUSA does not treat a cost as federally allowable merely because it was entered in the intake. The applicant should reconcile the narrative, line-item budget, quotes, calculations, and requested federal share before submission.",
        "Sustainability\n" + f"The sustainability section should explain which project benefits or capabilities {org} intends to maintain after the federal period and identify only realistic, applicant-supported continuation resources. Depending on the project, those may include institutional adoption, operating revenue, future grants, partner commitments, maintenance planning, dissemination, commercialization, or integration into ongoing operations. No continuation funding is assumed in this draft.",
        "Applicant Validation Required Before Submission\n" + f"This is a customized working proposal draft, not an agency approval or eligibility determination. {org} must verify the current notice for {g_title}, confirm applicant eligibility, replace or substantiate any draft assumption, finalize all numerical targets and budget details, complete required forms and attachments, obtain signatures/certifications, and submit through the official channel by the controlling deadline.",
    ]
    return "\n\n".join(sections)'''
server = server[:n_start] + narrative_fn + server[n_end:]

server = server.replace('from reportlab.platypus import Paragraph', 'from reportlab.platypus import Paragraph, Spacer, SimpleDocTemplate')
p_start = server.index("def make_pdf(")
p_end = server.index("\n\ndef ", p_start + 20)
pdf_fn = '''def make_pdf(order_id: str, payload: Dict[str, Any]) -> str:
    """Generate a paginated proposal PDF with protected header/footer space."""
    os.makedirs(PDF_DIR, exist_ok=True)
    pdf_path = os.path.join(PDF_DIR, f"{order_id}.pdf")
    created_at = _now_utc()
    def esc(value: Any) -> str:
        return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    styles = getSampleStyleSheet()
    body = styles["BodyText"].clone("GrantForgeBody"); body.fontName = "Helvetica"; body.fontSize = 10; body.leading = 14; body.spaceAfter = 8
    heading = styles["Heading2"].clone("GrantForgeHeading"); heading.fontName = "Helvetica-Bold"; heading.fontSize = 12; heading.leading = 15; heading.spaceBefore = 8; heading.spaceAfter = 6
    small = styles["BodyText"].clone("GrantForgeSmall"); small.fontName = "Helvetica"; small.fontSize = 9; small.leading = 12; small.spaceAfter = 5
    doc = SimpleDocTemplate(pdf_path, pagesize=letter, leftMargin=54, rightMargin=54, topMargin=72, bottomMargin=78, title=f"GrantForgeUSA Proposal Draft - {order_id}", author="GrantForgeUSA, LLC")
    def page_frame(c, _doc):
        c.saveState(); c.setFont("Helvetica-Bold", 11); c.drawString(54, 756, "GrantForgeUSA | Proposal Draft"); c.setFont("Helvetica", 8.5); c.drawString(54, 742, f"Order: {order_id} | Created: {created_at}"); c.setFont("Helvetica-Oblique", 8); c.drawString(54, 36, "Customized drafting service - verify against the current official notice before submission."); c.setFont("Helvetica", 8); c.drawRightString(558, 36, f"Page {_doc.page}"); c.restoreState()
    story = []
    draft_body = payload.get("draft_body")
    if isinstance(draft_body, str) and draft_body.strip():
        story.append(Paragraph("Grant Narrative", heading))
        for block in draft_body.split("\n\n"):
            block = block.strip()
            if not block: continue
            lines = block.split("\n", 1)
            if len(lines) == 2 and len(lines[0]) <= 90:
                story.append(Paragraph(esc(lines[0]), heading)); story.append(Paragraph(esc(lines[1]).replace("\n", "<br/>"), body))
            else:
                story.append(Paragraph(esc(block).replace("\n", "<br/>"), body))
    else:
        story.append(Paragraph("GrantForgeUSA Order Details", heading))
        for key, value in payload.items(): story.append(Paragraph(f"<b>{esc(key)}:</b> {esc(value)}", body))
    story.append(Spacer(1, 10)); story.append(Paragraph("Grant Opportunity Details", heading))
    details = [("Project title", payload.get("projectTitle", "")), ("Applicant type", payload.get("category", "")), ("Requested amount", f"${_safe_float(payload.get('amountRequested'), 0):,.2f}"), ("Service fee", f"${_safe_float(payload.get('price'), 0):,.2f}"), ("Recommended opportunity", payload.get("grant_title", "")), ("Program", payload.get("grant_program", "")), ("Deadline", payload.get("grant_deadline", ""))]
    for label, value in details: story.append(Paragraph(f"<b>{esc(label)}:</b> {esc(value)}", body))
    grant_url = _safe_grants_url(payload.get("grant_url") or "")
    if grant_url: story.append(Paragraph(f'<b>Official opportunity:</b> <a href="{esc(grant_url)}">{esc(grant_url)}</a>', body))
    recommendations = payload.get("recommendations") if isinstance(payload.get("recommendations"), list) else []
    if recommendations:
        story.append(Spacer(1, 6)); story.append(Paragraph("Other Screened Opportunities", heading))
        for item in recommendations[:10]:
            if not isinstance(item, dict): continue
            title = esc(item.get("title") or "Federal funding opportunity"); url = _safe_grants_url(item.get("program_url") or item.get("url") or "")
            story.append(Paragraph(f'• <a href="{esc(url)}">{title}</a>' if url else f"• {title}", small))
    story.append(Spacer(1, 12)); story.append(Paragraph("<b>Final review notice:</b> GrantForgeUSA is an independent private drafting service. The customer must verify applicant eligibility, all facts, the current funding notice, required forms, certifications, attachments, budget, and final submission. Funding is not guaranteed. Customized drafting services are final-sale subject to the Terms of Service and applicable law.", small))
    doc.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    return pdf_path'''
server = server[:p_start] + pdf_fn + server[p_end:]
server_path.write_text(server)

# Tests
ftest_path = Path("frontend/grantforge-frontend/tests/integration.test.mjs")
ftest = ftest_path.read_text()
ftest = replace_once(
    ftest,
    '''test("approved public pricing tiers are present and legacy flat price is absent", () => {
  for (const price of ["$9.99", "$49.99", "$99.99", "$199.99"]) {
    assert.ok(appSource.includes(price), `missing ${price}`);
  }
  assert.equal(appSource.includes("$2,500"), false);
  assert.ok(appSource.includes("serviceFeeFor"));
});''',
    '''test("one flat public draft price is used for every supported applicant", () => {
  assert.ok(appSource.includes('const FLAT_DRAFT_PRICE = "$49.99"'));
  assert.equal(appSource.includes("$9.99"), false);
  assert.equal(appSource.includes("$99.99"), false);
  assert.equal(appSource.includes("$199.99"), false);
  assert.ok(appSource.includes("One flat price for every supported applicant type and funding amount"));
});''',
    "frontend pricing test",
)
ftest = ftest.replace('  assert.ok(appSource.includes("all sales are final and non-refundable except where required by law"));', '  assert.ok(appSource.includes("customized drafting service immediately after payment"));\n  assert.ok(appSource.includes("final and non-refundable once generation begins"));')
anchor = '''test("technology is positioned as proprietary software without public AI branding", () => {
  assert.ok(appSource.includes("proprietary software"));
  assert.equal(/\\bAI\\b/.test(appSource), false);
});'''
ftest = replace_once(ftest, anchor, anchor + '''\n\ntest("public intake includes higher education and no student-aid surface", () => {
  assert.ok(appSource.includes("College / University / Research Institution"));
  assert.ok(appSource.includes("principal investigator"));
  assert.equal(/\\bFAFSA\\b/i.test(appSource), false);
  assert.equal(/student aid/i.test(appSource), false);
});''', "higher education frontend test")
ftest_path.write_text(ftest)

btest_path = Path("backend/tests/test_v11_server.py")
btest = btest_path.read_text()
if "def test_flat_pricing_for_all_applicant_types()" not in btest:
    btest += '''\n\n\ndef test_flat_pricing_for_all_applicant_types():
    categories = ["K-12 School / District / Educator", "College / University / Research Institution", "Church / Faith Organization", "501(c)(3) Nonprofit", "Small Business", "For-Profit Organization", "City / County / Local Government", "State Government / Agency", "Tribal Government / Organization", "Public Housing Authority", "Individual / Independent Applicant", "Other Eligible Applicant"]
    for category in categories:
        for budget in (1, 100000, 5000000, 500000000):
            assert srv.price_for(category, budget) == pytest.approx(49.99)


def test_higher_ed_uses_official_eligibility_codes():
    assert srv._is_eligible_for_applicant({"eligibility_codes": ["06"]}, "HIGHER_ED") is True
    assert srv._is_eligible_for_applicant({"eligibility_codes": ["20"]}, "HIGHER_ED") is True
    assert srv._is_eligible_for_applicant({"eligibility_codes": ["23"]}, "HIGHER_ED") is False


def test_narrative_does_not_invent_default_outcomes_or_capacity():
    grant = {"title": "Research Opportunity", "program": "Federal Program", "deadline": "2027-01-01", "max_amount": 500000, "summary": "Supports rigorous research and documented project outcomes."}
    payload = _payload("Example University", "research, education, rural", "College / University / Research Institution")
    text = srv.build_narrative(payload, grant)
    assert "20%" not in text and "70%" not in text and "90%" not in text
    assert "does not assume" in text
    assert "Applicant Validation Required Before Submission" in text
'''
btest_path.write_text(btest)

# Docs
readme_path = Path("README.md")
readme = readme_path.read_text()
readme = readme.replace('- displays the approved pricing model: $9.99 / $49.99 / $99.99 / $199.99;', '- uses one $49.99 flat price for a selected full customized proposal draft;')
readme = readme.replace('''| Applicant segment | Planned standard pilot price |
|---|---:|
| Teacher or classroom project | $9.99 |
| Organization with annual operating budget up to $500,000 | $49.99 |
| Organization with annual operating budget from $500,000 to $2 million | $99.99 |
| Organization with annual operating budget above $2 million | $199.99 |''', '''| Service | Price |
|---|---:|
| Federal opportunity search, screening, official links, and preview | Free |
| One selected customized full proposal draft | $49.99 |''')
readme_path.write_text(readme)

# Final source sanity checks
public = app_path.read_text()
for banned in ("$9.99", "$99.99", "$199.99", "FAFSA"):
    if banned in public:
        raise SystemExit(f"public frontend still contains banned term: {banned}")
if "College / University / Research Institution" not in public:
    raise SystemExit("higher-ed applicant option missing")
if "FLAT_DRAFT_PRICE" not in server_path.read_text():
    raise SystemExit("flat price backend missing")
print("Release-candidate patch completed")
