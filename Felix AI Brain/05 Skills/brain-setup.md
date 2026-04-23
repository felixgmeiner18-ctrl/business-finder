# Skill: Brain Setup

Generate a personalized CLAUDE.md by scanning the vault structure and interviewing the user. The result is a fully populated context file that makes Claude an effective thinking partner for this vault.

## When to Use

- User just copied the vault template and needs to set it up
- CLAUDE.md is missing or contains only placeholder text
- User explicitly asks to set up or initialize their vault

## How It Works

1. Scan the vault folder structure silently
2. Interview the user in 5 rounds (one per CLAUDE.md section)
3. Generate the full CLAUDE.md in the user's own voice
4. Show it for review — make targeted edits until they're happy
5. Write the file and suggest next steps

If a CLAUDE.md already exists with real content, ask the user whether they want to start fresh or build on what's there.

## Phase 1: Scan the Vault

Before asking anything, scan the folder structure:

```bash
# Top-level folders
ls -d */

# Project subfolders
ls -d "03 Projects"/*/ 2>&1 || echo "No projects yet"
```

Record:
- Which system folders exist (Weekly Reviews, Books, Chess Moves, etc.)
- Which project folders exist under `03 Projects/`
- Whether CLAUDE.md or GOALS.md already exist

You'll use this to auto-populate the Folder Structure section.

## Phase 2: Interview (5 Rounds)

Conduct conversationally. After each round, **briefly summarize** what you captured so the user can correct anything before you move on.

**Pacing:** Some rounds list 3-5 sub-questions. Group related ones naturally — it's fine to ask 4-5 at once if they flow together. If an answer is thin, probe once — then move on. Don't interrogate.

Use AskUserQuestion for structured choices (Round 3 communication style). Everything else is open conversation.

---

### Round 1: Who You Are & Your Purpose

Ask:
- **What do you want to call this vault?** (Default: use the vault folder name)
- **What do you do?** Creator, developer, designer, entrepreneur, student — what's the one-liner?
- **What's your purpose?** The thing that drives you, the mission behind the work.
- **What do you love doing?** The activities that energize you — not obligations, the stuff you'd do for free.
- **What do you refuse to do?** Values, hard lines, things you won't compromise on.
- **Any personal context** that shapes how you work? (faith, family, health goals, location, life stage, etc.)

**Goal:** Capture their identity in THEIR voice. This should sound like them talking, not a LinkedIn bio.

---

### Round 2: What You Want Claude to Do

Ask:
- **At this top level** (above individual projects), what do you want Claude to help with?
- **What kind of thinking partner** do you need? Strategic planning? Accountability? Creative brainstorming? Decision-making? All of the above?
- **What's the prime directive?** If Claude could only do ONE thing well in this vault, what should it be?

**Goal:** Define Claude's role so it knows what's in-scope here vs. what belongs in project-level CLAUDE.md files.

---

### Round 3: Rules & Boundaries

Start with AskUserQuestion for communication style:

**Question:** "How should Claude communicate with you?"
- **Blunt and direct** — Challenge me, don't sugarcoat, call me out when I'm wrong
- **Supportive but honest** — Encourage me, but flag real issues when they matter
- **Balanced** — Match my energy, be direct when it counts
- (user can pick Other for custom)

Then ask open-ended:
- **Any specific rules or pet peeves?** (e.g., "don't give me 10 options when I need to pick one", "always end with a suggested next action")
- **How should Claude handle files?** (e.g., prefix AI-generated files with `(C)`, ask before editing existing notes)
- **Anything Claude should NEVER do** in this vault?

**Defaults if user has no file-handling preference:** Use `(C)` prefix on AI-generated files. Don't edit existing files without permission.

**Goal:** Concrete, actionable rules — not vague preferences.

---

### Round 4: Strengths & Weaknesses

Ask:
- **What are you genuinely great at?** Skills, natural talents, unfair advantages.
- **What are your blind spots or recurring failure modes?** The patterns that bite you.
- **What do you default to when stressed or overwhelmed?** (e.g., "I retreat to busy-work", "I over-plan and under-ship")

**Goal:** Honest self-assessment Claude can reference to give better advice. Specific > generic. "I spread too thin across too many projects" beats "bad at time management."

**Note:** The stress-default answer goes into the Weaknesses section — it's a behavioral pattern, not a separate category.

---

### Round 5: Goals & Current Progress

Ask:
- **What's your main goal right now?** Financial target, launch milestone, growth number — make it concrete.
- **Where are you today?** Current income, progress, resources, runway.
- **What's the plan to get there?** Even rough steps. The strategy connecting today to the goal.
- **Any risks or time-sensitive factors?** Deadlines, runway limits, dependencies.

**Goal:** Real numbers and timelines wherever possible. Push gently for specifics — "$6k/mo by Q3" is 10x more useful than "make more money."

**If the plan is vague:** That's fine — write what they gave you. Suggest a strategic thinking session (Chess Moves) to flesh it out later.

---

## Phase 3: Generate CLAUDE.md

After all 5 rounds, assemble the CLAUDE.md using this template. **Write in the user's voice** — mirror their language, don't sanitize it.

~~~markdown
# [Vault Name] — Claude Context File

[One sentence: what this vault is and who it serves.]


## Who I Am & My Purpose

[From Round 1. Write 2-3 paragraphs in first person. Paragraph 1: what they do. Paragraph 2: their purpose and what energizes them. Paragraph 3: what they refuse to do, values, personal context.]


## Claude's Purpose in This Level

[From Round 2. Open with a framing sentence, then a bulleted list of Claude's responsibilities, then the prime directive as a closing paragraph.]


## Claude's Rules & Boundaries

[From Round 3. Bulleted list of concrete rules. Bold the key phrase in each bullet.]


## Folder Structure

```
[Vault Name]/
├── CLAUDE.md              ← You are here
├── GOALS.md               ← Goals, progress, master plan
[Auto-generated from Phase 1 scan. List every system folder and Projects subfolder with ← short description]
```


## My Strengths & Weaknesses

**Strengths:**
[Bulleted list from Round 4]

**Weaknesses & blind spots:**
[Bulleted list from Round 4]


## My Goals & Current Progress

[From Round 5. Include: the target number/milestone, current state with real numbers, the step-by-step plan, risks/runway.]


## Weekly Update

> **Last updated:** _[update this each week]_

- What's working:
- What's not working:
- What I'm sitting on / need to decide:
- What I'm feeling pulled toward:
- Any deadlines or time-sensitive things:


## My Current Projects & Overviews

_No projects yet. Use the New Project skill to create your first project — it will automatically add it here._
~~~

**Critical rules for generation:**
- **Don't fabricate.** If a section got a thin answer, write a thin section. Never pad with assumptions.
- **Use their words.** If they said "I build cool shit with AI," write that. Don't rewrite it as "I develop innovative AI solutions."
- **Folder structure is auto-detected.** Don't ask them to describe folders you already scanned.
- **Weekly Update is always a blank template.** Don't pre-fill it.

## Phase 4: Review & Confirm

Display the full generated CLAUDE.md to the user. Ask:

> "Here's your CLAUDE.md — read through it. Anything you want to change, add, or remove before I save it?"

**Revisions:** Make targeted edits to the specific sections the user flags. Don't regenerate the whole document — just fix what they call out. Loop until they say it's good.

Only write the file after explicit confirmation. Save to `CLAUDE.md` at vault root.

## Phase 5: Next Steps

After writing, tell the user:

1. **CLAUDE.md is live** — Claude reads it at the start of every session in this vault
2. **Update the Weekly Update section** each week to keep Claude current on what's happening
3. **Create your first project** — use the New Project skill to set up a project folder under `03 Projects/` with its own CLAUDE.md. Projects get added to the "My Current Projects & Overviews" section automatically.
4. **If your plan or goals feel vague** — run a Chess Moves strategic thinking session to flesh them out
5. **First session idea** — try a weekly review or Chess Moves session to break in the new setup and see Claude in action
