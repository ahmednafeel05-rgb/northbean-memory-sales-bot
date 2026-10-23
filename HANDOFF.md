# How to continue in Claude Code

## 1. Set up the folder (once)
1. Create an empty project folder, e.g. `northbean-memory-bot`, and `git init` it.
2. Copy everything from this package into it, keeping the folders:
   ```
   CLAUDE.md
   docs/DESIGN_BRIEF.md
   data/products.json
   data/personas.json
   evals/golden.jsonl
   ```
3. Make sure the Genesis kit is installed on your machine (`./install.sh` from the genesis-kit repo).
4. Get free API keys for Gemini and Groq. Put them in a `.env` file (never commit it):
   ```
   GEMINI_API_KEY=...
   GROQ_API_KEY=...
   ```

## 2. First message to paste in Claude Code
Open a terminal in the project folder, run `claude`, then paste:

> Read CLAUDE.md and docs/DESIGN_BRIEF.md fully. This is my portfolio project, a sales bot
> with an intelligent memory system. Run the Genesis setup (G0–G6) for this repo using the
> brief as the input: answer G0 from the brief, write DONE.html with the invariants from
> section 10 and the definition of done, write PLAN.md from the sprints in section 13 with
> their demo commands, add the invariants to context-graph.json, write the ADRs from section
> 16, and fill KICKOFF.md. Ask me only about decisions the brief does not already settle.
> Then show me DONE.html and PLAN.md for approval before starting S1.

## 3. For every sprint after that
> Run KICKOFF.md. Build the next sprint in PLAN.md through the L1 BUILD loop with all five
> gates and end through L4 VERIFY. When done, give me a beginner-level dry run: one example
> input traced through the files you touched.

## 4. Your job during the build
- Approve DONE.html and PLAN.md once (they are locked after that).
- Read each sprint's dry run, and ask "why" about anything unclear.
- Unblock the loop when it asks (rate limits, a failed check three times, a decision).
- Try the demo command yourself at the end of each sprint.
