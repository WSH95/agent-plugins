# Writing project documentation

Write project records as working notes for another developer. Keep the prose
plain, factual, and easy to scan.

- State what happened, what remains, and what evidence supports it.
- Use direct sentences and simple verbs. Keep headings in sentence case.
- Keep useful uncertainty. Name a source when the source is available.
- Leave out sales language, inflated claims, vague attribution, filler,
  chatbot greetings and closings, decorative emoji, and unnecessary bold
  labels.
- Do not invent facts or remove qualifications while editing for tone.
- Match a writing sample only when the user identifies it as their own.
  Otherwise, use neutral technical prose.
- Apply these rules only to text being created or changed. Do not restyle
  historical entries or unrelated user prose.
- Preserve YAML front matter, JSON, code blocks, commands, link targets,
  identifiers, managed markers, required headings, and timestamp delimiters.

## Optional Humanizer pass

If the agent runtime provides a skill named `humanizer`, use it after drafting
new prose and before presenting or writing the result. Use embedded mode for a
passage and file mode for a named file. Give it only the text in scope, and do
not install it automatically.

After the pass, check that the rewrite did not add or remove any fact, name,
number, date, quote, citation, command, link, or qualification. Treat any such
change as an error.

This guide follows the same editing principles as the optional Humanizer skill,
which draws on [Wikipedia's signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing).
