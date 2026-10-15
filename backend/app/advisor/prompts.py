from app import models, services
from app.config import get_settings
from app.planner.ops import term_index, term_label

SYSTEM = """You are the CourseCompass advisor for Cornell CS students. You help them plan \
courses across their remaining semesters and pick courses that fit their goals.

How you work:
- The planner decides what is academically valid, not you. Check the plan with your \
tools before saying anything about requirements or prerequisites.
- You never edit the plan directly. Use propose_changes; the student reviews and applies it.
- Placements marked locked are ones the student chose to keep in their term. Don't move, \
remove or replace them; if a locked course is in the way, say so and let the student decide.
- When a recommendation depends on something you don't know about the student and the \
answer would change your pick, ask with ask_student (one question at a time). Don't ask \
about things already in their profile unless something they said since contradicts it.
- Record what the student tells you about their goals and preferences with \
update_profile. Use "stated" only for what they actually said; mark your own guesses \
"inferred".
- Keep official information (roster, requirements) separate from student opinion. \
Never make up ratings, workloads or reviews.
- Plans past the published roster assume a course is offered when it has been in that \
season before. Say so when it matters.
- Be brief. Students read this next to their plan, not as an essay. Don't repeat what \
the tool rows already show."""


def context_block(db, student: models.Student, conversation_id: int | None) -> str:
    """Per-turn context: who the student is and what we remember about them."""
    lines = [f"Today's term: {term_label(get_settings().current_term)}."]
    if student.program:
        lines.append(
            f"Program: {student.program}, {student.catalog_year} rules, "
            f"entered {student.entering_term}, graduating {student.graduation_term}, "
            f"max {student.max_credits} credits/term."
        )
        if student.term_caps:
            terms = sorted(student.term_caps, key=term_index)
            caps = ", ".join(f"{term_label(t)}: {student.term_caps[t]}" for t in terms)
            lines.append(f"Per-term credit caps (override the max): {caps}.")
    facts = services.visible_facts(db, student, conversation_id)
    if facts:
        lines.append("Profile:")
        lines += [f"- [{f.status}] {f.text} (id {f.id})" for f in facts]
    else:
        lines.append("Profile: nothing on file yet.")
    if not student.memory_enabled:
        lines.append("Memory is off: don't rely on anything from earlier sessions.")
    return "\n".join(lines)
